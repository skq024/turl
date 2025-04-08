# data_processor.py
import os
import json
import logging
import pandas as pd
import geopandas as gpd
from shapely.geometry import Point, Polygon, MultiPolygon
from datetime import datetime
from sqlalchemy import create_engine

# Configure logging
logging.basicConfig(
    filename=f'data_processor_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log',
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)

class CensusDataProcessor:
    """Process scraped Census QuickFacts data and prepare it for database loading"""
    
    def __init__(self, input_dir, output_dir, db_connection_string=None):
        self.input_dir = input_dir
        self.output_dir = output_dir
        self.db_connection_string = db_connection_string
        
        # Ensure output directory exists
        os.makedirs(output_dir, exist_ok=True)
        
        # Initialize dataframes to hold processed data
        self.locations_df = pd.DataFrame()
        self.demographics_df = pd.DataFrame()
        
    def process_all_files(self):
        """Process all JSON files in the input directory"""
        logging.info(f"Processing files from {self.input_dir}")
        
        files_processed = 0
        files_with_errors = 0
        
        # Get all JSON files
        json_files = [f for f in os.listdir(self.input_dir) if f.endswith('.json')]
        
        for filename in json_files:
            try:
                file_path = os.path.join(self.input_dir, filename)
                logging.info(f"Processing {file_path}")
                
                # Load the JSON data
                with open(file_path, 'r') as f:
                    data = json.load(f)
                
                # Process the data
                self._process_location(data)
                self._process_demographics(data)
                
                files_processed += 1
            except Exception as e:
                logging.error(f"Error processing {filename}: {str(e)}")
                files_with_errors += 1
        
        logging.info(f"Processed {files_processed} files. Errors in {files_with_errors} files.")
        
        # Save processed data to CSV and/or database
        self._save_processed_data()
        
    def _process_location(self, data):
        """Extract and process location data"""
        try:
            if not data.get('name') or not data.get('type'):
                return
            
            # Create a GeoDataFrame for the location
            location_data = {
                'location_id': self._generate_location_id(data),
                'name': data.get('name'),
                'type': data.get('type'),
                'fips_code': data.get('fips_code'),
                'url': data.get('url'),
                'scraped_at': data.get('scraped_at')
            }
            
            # Process coordinates if available
            coordinates = data.get('coordinates')
            if coordinates:
                # Check if coordinates are for a point or polygon
                if isinstance(coordinates, list) and len(coordinates) == 2 and isinstance(coordinates[0], (int, float)):
                    # It's a point (lon, lat)
                    location_data['geometry'] = Point(coordinates)
                elif isinstance(coordinates, list) and len(coordinates) > 0:
                    # It's likely a polygon or multipolygon
                    if isinstance(coordinates[0], list) and isinstance(coordinates[0][0], list):
                        # MultiPolygon
                        polygons = []
                        for polygon_coords in coordinates:
                            polygons.append(Polygon(polygon_coords))
                        location_data['geometry'] = MultiPolygon(polygons)
                    else:
                        # Single Polygon
                        location_data['geometry'] = Polygon(coordinates)
            else:
                location_data['geometry'] = None
            
            # Add to the locations dataframe
            location_df = gpd.GeoDataFrame([location_data], geometry='geometry')
            self.locations_df = pd.concat([self.locations_df, location_df], ignore_index=True)
            
        except Exception as e:
            logging.error(f"Error processing location data: {str(e)}")
    
    def _process_demographics(self, data):
        """Extract and process demographic data"""
        try:
            demographics = data.get('demographics', {})
            if not demographics:
                return
                
            location_id = self._generate_location_id(data)
            
            for category, category_data in demographics.items():
                time_series = category_data.get('time_series', {})
                
                for year, value in time_series.items():
                    demographic_row = {
                        'location_id': location_id,
                        'category': category,
                        'raw_category': category_data.get('raw_category', category),
                        'year': year,
                        'value': value
                    }
                    
                    # Add to demographics dataframe
                    self.demographics_df = pd.concat(
                        [self.demographics_df, pd.DataFrame([demographic_row])], 
                        ignore_index=True
                    )
                    
        except Exception as e:
            logging.error(f"Error processing demographic data: {str(e)}")
    
    def _generate_location_id(self, data):
        """Generate a unique ID for the location"""
        # Use FIPS code if available
        if data.get('fips_code'):
            return f"{data.get('type')}_fips_{data.get('fips_code')}"
        
        # Otherwise use name and type
        normalized_name = data.get('name', '').lower().replace(' ', '_')
        return f"{data.get('type')}_{normalized_name}"
    
    def _save_processed_data(self):
        """Save processed data to CSV files and/or database"""
        try:
            # Save to CSV files
            locations_csv = os.path.join(self.output_dir, 'locations.csv')
            demographics_csv = os.path.join(self.output_dir, 'demographics.csv')
            
            # Convert GeoDataFrame to CSV
            if not self.locations_df.empty:
                # Save as GeoJSON for preserving geometry
                locations_geojson = os.path.join(self.output_dir, 'locations.geojson')
                self.locations_df.to_file(locations_geojson, driver='GeoJSON')
                
                # Also save as CSV with WKT geometry
                self.locations_df['geometry_wkt'] = self.locations_df['geometry'].apply(
                    lambda x: x.wkt if x else None
                )
                locations_df_csv = self.locations_df.drop(columns=['geometry'])
                locations_df_csv.to_csv(locations_csv, index=False)
                
                logging.info(f"Saved locations data to {locations_geojson} and {locations_csv}")
            
            if not self.demographics_df.empty:
                self.demographics_df.to_csv(demographics_csv, index=False)
                logging.info(f"Saved demographics data to {demographics_csv}")
            
            # Save to database if connection string provided
            if self.db_connection_string:
                self._save_to_database()
        
        except Exception as e:
            logging.error(f"Error saving processed data: {str(e)}")
    
    def _save_to_database(self):
        """Save processed data to database tables"""
        try:
            engine = create_engine(self.db_connection_string)
            
            # Save locations to database
            if not self.locations_df.empty:
                # Use GeoPandas to_postgis for geometry column
                self.locations_df.to_postgis(
                    name='locations',
                    con=engine,
                    if_exists='append',
                    index=False
                )
                logging.info("Saved locations data to database")
            
            # Save demographics to database
            if not self.demographics_df.empty:
                self.demographics_df.to_sql(
                    name='demographics',
                    con=engine,
                    if_exists='append',
                    index=False
                )
                logging.info("Saved demographics data to database")
                
        except Exception as e:
            logging.error(f"Error saving to database: {str(e)}")


if __name__ == "__main__":
    # Example usage
    processor = CensusDataProcessor(
        input_dir='./scraped_data',
        output_dir='./processed_data',
        db_connection_string='postgresql://username:password@localhost:5432/census_db'
    )
    processor.process_all_files()