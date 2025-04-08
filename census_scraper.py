# census_scraper.py
import scrapy
import json
import re
import logging
from scrapy.crawler import CrawlerProcess
from datetime import datetime
from urllib.parse import urljoin

class CensusQuickFactsSpider(scrapy.Spider):
    name = 'census_quickfacts'
    allowed_domains = ['census.gov']
    start_urls = ['https://www.census.gov/quickfacts/fact/table/US/PST045222']
    
    # Track visited URLs to avoid duplicates
    visited_urls = set()
    
    # Configure logging
    logging.basicConfig(
        filename=f'census_scraper_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log',
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(message)s'
    )
    
    def parse(self, response):
        """Main parsing method for QuickFacts pages"""
        # Extract current location info
        location_data = self._extract_location_data(response)
        if not location_data:
            return
            
        # Extract demographic data
        demographic_data = self._extract_demographic_data(response)
        
        # Combine location and demographic data
        data = {**location_data, **demographic_data}
        
        # Save the data
        self._save_data(data)
        
        # Find and follow links to other locations (states, counties, cities)
        self._follow_location_links(response)
    
    def _extract_location_data(self, response):
        """Extract location metadata (name, type, geo coordinates)"""
        try:
            # Extract location name and type
            breadcrumb = response.css('nav.breadcrumb-v2 span::text').getall()
            
            if not breadcrumb or len(breadcrumb) < 2:
                return None
                
            location_name = breadcrumb[-1].strip()
            location_type = self._determine_location_type(breadcrumb, response)
            
            # Extract geospatial data (coordinates) if available
            geo_script = response.css('script:contains("geoJson")').get()
            coordinates = None
            
            if geo_script:
                coordinates = self._extract_coordinates(geo_script)
            
            return {
                'name': location_name,
                'type': location_type,
                'coordinates': coordinates,
                'fips_code': self._extract_fips_code(response),
                'url': response.url,
                'scraped_at': datetime.now().isoformat()
            }
        except Exception as e:
            logging.error(f"Error extracting location data: {str(e)}")
            return None
    
    def _determine_location_type(self, breadcrumb, response):
        """Determine the type of location (state, county, city, town, ZIP)"""
        url_path = response.url.lower()
        breadcrumb_text = ' '.join(breadcrumb).lower()
        
        if 'zip' in url_path or 'zcta' in url_path:
            return 'zipcode'
        elif 'county' in url_path or 'county' in breadcrumb_text:
            return 'county'
        elif 'city' in url_path or 'city' in breadcrumb_text:
            return 'city'
        elif 'town' in url_path or 'town' in breadcrumb_text:
            return 'town'
        elif 'state' in breadcrumb_text or len(breadcrumb) == 2:
            return 'state'
        else:
            return 'unknown'
    
    def _extract_coordinates(self, geo_script):
        """Extract geospatial coordinates from script tag"""
        try:
            # Look for GeoJSON in the script
            geojson_match = re.search(r'var\s+geoJson\s*=\s*(\{.*?\});', geo_script, re.DOTALL)
            if geojson_match:
                geo_json_str = geojson_match.group(1)
                # Clean up the string to make it valid JSON
                geo_json_str = re.sub(r'(\w+):', r'"\1":', geo_json_str)
                geo_json_str = re.sub(r',\s*}', '}', geo_json_str)
                geo_json = json.loads(geo_json_str)
                
                # Extract coordinates based on GeoJSON structure
                if 'geometry' in geo_json and 'coordinates' in geo_json['geometry']:
                    return geo_json['geometry']['coordinates']
            return None
        except Exception as e:
            logging.error(f"Error extracting coordinates: {str(e)}")
            return None
    
    def _extract_fips_code(self, response):
        """Extract FIPS code if available"""
        try:
            # FIPS code is often in the URL or in specific elements
            url = response.url
            fips_match = re.search(r'fips=(\d+)', url)
            if fips_match:
                return fips_match.group(1)
                
            # Try to find it in the page content
            fips_elem = response.css('span:contains("FIPS Code")').xpath('./following-sibling::span/text()').get()
            if fips_elem:
                return fips_elem.strip()
                
            return None
        except Exception as e:
            logging.error(f"Error extracting FIPS code: {str(e)}")
            return None
    
    def _extract_demographic_data(self, response):
        """Extract demographic data from the QuickFacts table"""
        demographic_data = {}
        
        try:
            # Extract the data table
            table_rows = response.css('table.data-grid tr')
            
            # Extract historical years from column headers
            years = self._extract_years(response)
            
            for row in table_rows:
                # Get the demographic category
                category = row.css('th::text').get()
                if not category:
                    continue
                    
                category = category.strip()
                
                # Get values for each year
                values = row.css('td::text').getall()
                if not values or len(values) == 0:
                    continue
                
                # Clean up values
                values = [v.strip() for v in values if v.strip()]
                
                # Map values to years
                time_series = {}
                for i, year in enumerate(years):
                    if i < len(values):
                        time_series[year] = self._normalize_value(values[i])
                
                # Store in the demographic data
                demographic_data[self._normalize_key(category)] = {
                    'raw_category': category,
                    'time_series': time_series
                }
            
            return {'demographics': demographic_data}
        except Exception as e:
            logging.error(f"Error extracting demographic data: {str(e)}")
            return {'demographics': {}}
    
    def _extract_years(self, response):
        """Extract years from the table headers"""
        try:
            # Get column headers which often contain years
            headers = response.css('table.data-grid th.gridHeaderColumnRight::text').getall()
            years = []
            
            for header in headers:
                # Look for years in the format YYYY
                year_match = re.search(r'(19|20)\d{2}', header)
                if year_match:
                    years.append(year_match.group(0))
                else:
                    # If no year found, use the header as is
                    years.append(header.strip())
            
            return years if years else ["Current"]
        except Exception as e:
            logging.error(f"Error extracting years: {str(e)}")
            return ["Current"]
    
    def _normalize_key(self, key):
        """Normalize category names for consistent keys"""
        # Remove special characters and convert to lowercase
        normalized = re.sub(r'[^\w\s]', '', key).lower()
        # Replace spaces with underscores
        normalized = re.sub(r'\s+', '_', normalized)
        return normalized
    
    def _normalize_value(self, value):
        """Normalize and convert values to appropriate types"""
        if not value or value == 'N/A' or value == '-':
            return None
            
        # Remove commas from numbers
        clean_value = value.replace(',', '')
        
        # Try to convert to numeric if possible
        if '%' in clean_value:
            # Handle percentages
            try:
                return float(clean_value.replace('%', '')) / 100
            except ValueError:
                return value
        else:
            # Try to convert to int or float
            try:
                if '.' in clean_value:
                    return float(clean_value)
                else:
                    return int(clean_value)
            except ValueError:
                return value
    
    def _save_data(self, data):
        """Save extracted data to JSON file"""
        if not data or not data.get('name'):
            return
            
        filename = f"census_data_{data['type']}_{self._normalize_key(data['name'])}.json"
        
        with open(filename, 'w') as f:
            json.dump(data, f, indent=2)
        
        logging.info(f"Saved data for {data['name']} ({data['type']}) to {filename}")
    
    def _follow_location_links(self, response):
        """Find and follow links to other locations"""
        # Look for links to states
        state_links = response.css('map[name="state"] area::attr(href)').getall()
        for link in state_links:
            full_url = urljoin(response.url, link)
            if full_url not in self.visited_urls:
                self.visited_urls.add(full_url)
                yield scrapy.Request(full_url, callback=self.parse)
        
        # Look for links to counties
        county_links = response.css('a[href*="county"]::attr(href)').getall()
        for link in county_links:
            full_url = urljoin(response.url, link)
            if full_url not in self.visited_urls:
                self.visited_urls.add(full_url)
                yield scrapy.Request(full_url, callback=self.parse)
        
        # Look for links to cities and towns
        city_links = response.css('a[href*="city"]::attr(href), a[href*="town"]::attr(href)').getall()
        for link in city_links:
            full_url = urljoin(response.url, link)
            if full_url not in self.visited_urls:
                self.visited_urls.add(full_url)
                yield scrapy.Request(full_url, callback=self.parse)
        
        # Look for zip code links
        zip_links = response.css('a[href*="zip"]::attr(href), a[href*="zcta"]::attr(href)').getall()
        for link in zip_links:
            full_url = urljoin(response.url, link)
            if full_url not in self.visited_urls:
                self.visited_urls.add(full_url)
                yield scrapy.Request(full_url, callback=self.parse)


if __name__ == "__main__":
    # Define the process
    process = CrawlerProcess({
        'USER_AGENT': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'CONCURRENT_REQUESTS': 8,
        'DOWNLOAD_DELAY': 1,  # Polite scraping with 1-second delay
        'ROBOTSTXT_OBEY': True,
        'LOG_LEVEL': 'INFO'
    })
    
    # Start the crawling process
    process.crawl(CensusQuickFactsSpider)
    process.start()