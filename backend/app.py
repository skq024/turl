# app.py
from fastapi import FastAPI, HTTPException, Depends, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from typing import List, Dict, Optional, Any
from pydantic import BaseModel, Field
import json
import logging
from shapely.geometry import Point, Polygon, shape
from shapely.wkt import loads as wkt_loads
import geopandas as gpd
from datetime import datetime
import os

from redis_cache import GeoCache

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
)
logger = logging.getLogger(__name__)

# Load configuration from environment variables
DB_CONNECTION_STRING = os.getenv("DB_CONNECTION_STRING", "postgresql://username:password@postgres:5432/census_db")
REDIS_HOST = os.getenv("REDIS_HOST", "redis")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", None)
CACHE_TTL = int(os.getenv("CACHE_TTL", "3600"))

# Initialize FastAPI app
app = FastAPI(
    title="Geospatial Analytics API",
    description="API for geospatial data mining, visualization, and analytics",
    version="1.0.0",
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # For production, specify actual origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize database connection
engine = create_engine(DB_CONNECTION_STRING)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Initialize Redis cache
cache = GeoCache(
    host=REDIS_HOST,
    port=REDIS_PORT,
    password=REDIS_PASSWORD,
    ttl_seconds=CACHE_TTL
)

# Dependency to get DB session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Pydantic models for request/response validation
class Point(BaseModel):
    longitude: float
    latitude: float

class BoundingBox(BaseModel):
    min_longitude: float
    min_latitude: float
    max_longitude: float
    max_latitude: float

class GeoJSONPolygon(BaseModel):
    type: str
    coordinates: List[List[List[float]]]

class LocationResponse(BaseModel):
    location_id: str
    name: str
    type: str
    fips_code: Optional[str] = None
    geometry: Optional[Dict] = None
    distance_meters: Optional[float] = None

class DemographicResponse(BaseModel):
    location_id: str
    category: str
    raw_category: str
    year: str
    value: Optional[float] = None

class TimeSeriesResponse(BaseModel):
    location_id: str
    name: str
    category: str
    values: Dict[str, Optional[float]]

# Health check endpoint
@app.get("/health")
async def health_check():
    """Check API health status"""
    db_healthy = True
    redis_healthy = cache.health_check()
    
    try:
        # Check database connection
        db = SessionLocal()
        db.execute("SELECT 1")
        db.close()
    except Exception as e:
        logger.error(f"Database health check failed: {str(e)}")
        db_healthy = False
    
    return {
        "status": "healthy" if db_healthy and redis_healthy else "unhealthy",
        "database": "connected" if db_healthy else "disconnected",
        "cache": "connected" if redis_healthy else "disconnected",
        "timestamp": datetime.now().isoformat()
    }

# Endpoint to get all location types
@app.get("/api/location-types", response_model=List[str])
async def get_location_types(db: Session = Depends(get_db)):
    """Get all available location types"""
    # Check cache first
    cached_result = cache.get("location_types")
    if cached_result:
        return cached_result
    
    result = db.execute("SELECT DISTINCT type FROM census.locations").fetchall()
    location_types = [row[0] for row in result]
    
    # Cache the result
    cache.set("location_types", location_types)
    
    return location_types

# Endpoint to get all demographic categories
@app.get("/api/demographic-categories", response_model=List[str])
async def get_demographic_categories(db: Session = Depends(get_db)):
    """Get all available demographic categories"""
    # Check cache first
    cached_result = cache.get("demographic_categories")
    if cached_result:
        return cached_result
    
    result = db.execute("SELECT DISTINCT category FROM census.demographics").fetchall()
    categories = [row[0] for row in result]
    
    # Cache the result
    cache.set("demographic_categories", categories)
    
    return categories

# Endpoint to get all available years
@app.get("/api/years", response_model=List[str])
async def get_years(db: Session = Depends(get_db)):
    """Get all available years in the dataset"""
    # Check cache first
    cached_result = cache.get("years")
    if cached_result:
        return cached_result
    
    result = db.execute("SELECT DISTINCT year FROM census.demographics ORDER BY year").fetchall()
    years = [row[0] for row in result]
    
    # Cache the result
    cache.set("years", years)
    
    return years

# Endpoint to get locations by type
@app.get("/api/locations", response_model=List[LocationResponse])
async def get_locations(
    type: Optional[str] = None,
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db)
):
    """Get locations, optionally filtered by type"""
    # Generate cache key based on parameters
    cache_key = f"locations:{type or 'all'}:{limit}:{offset}"
    cached_result = cache.get(cache_key)
    
    if cached_result:
        return cached_result
    
    query = """
        SELECT 
            location_id, 
            name, 
            type, 
            fips_code, 
            ST_AsGeoJSON(geometry) as geometry_json
        FROM 
            census.locations
    """
    
    params = {}
    
    if type:
        query += " WHERE type = :type"
        params["type"] = type
    
    query += " ORDER BY name LIMIT :limit OFFSET :offset"
    params["limit"] = limit
    params["offset"] = offset
    
    result = db.execute(query, params).fetchall()
    
    locations = []
    for row in result:
        location = {
            "location_id": row[0],
            "name": row[1],
            "type": row[2],
            "fips_code": row[3],
            "geometry": json.loads(row[4]) if row[4] else None
        }
        locations.append(location)
    
    # Cache the result
    cache.set(cache_key, locations)
    
    return locations

# Endpoint to get a specific location by ID
@app.get("/api/locations/{location_id}", response_model=LocationResponse)
async def get_location(location_id: str, db: Session = Depends(get_db)):
    """Get a specific location by ID"""
    # Check cache first
    cached_result = cache.get(f"location:{location_id}")
    if cached_result:
        return cached_result
    
    query = """
        SELECT 
            location_id, 
            name, 
            type, 
            fips_code, 
            ST_AsGeoJSON(geometry) as geometry_json
        FROM 
            census.locations
        WHERE 
            location_id = :location_id
    """
    
    result = db.execute(query, {"location_id": location_id}).fetchone()
    
    if not result:
        raise HTTPException(status_code=404, detail="Location not found")
    
    location = {
        "location_id": result[0],
        "name": result[1],
        "type": result[2],
        "fips_code": result[3],
        "geometry": json.loads(result[4]) if result[4] else None
    }
    
    # Cache the result
    cache.set(f"location:{location_id}", location)
    
    return location

# Endpoint to find nearby locations from a point
@app.post("/api/nearby", response_model=List[LocationResponse])
async def find_nearby_locations(
    point: Point,
    distance_meters: float = Query(10000, gt=0),
    types: Optional[List[str]] = Query(None),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db)
):
    """Find locations near a given point within specified distance"""
    # Generate cache key for this query
    params = {
        "longitude": point.longitude,
        "latitude": point.latitude,
        "distance_meters": distance_meters,
        "types": types,
        "limit": limit
    }
    cached_result = cache.get_cached_query_result("nearby", params)
    if cached_result:
        return cached_result
    
    # Convert types list to SQL array if provided
    types_clause = ""
    query_params = {
        "longitude": point.longitude,
        "latitude": point.latitude,
        "distance": distance_meters,
        "limit": limit
    }
    
    if types and len(types) > 0:
        types_clause = "AND l.type = ANY(:types)"
        query_params["types"] = types
    
    query = f"""
        SELECT 
            l.location_id, 
            l.name, 
            l.type, 
            l.fips_code, 
            ST_AsGeoJSON(l.geometry) as geometry_json,
            ST_Distance(
                l.geometry::geography, 
                ST_SetSRID(ST_MakePoint(:longitude, :latitude), 4326)::geography
            ) as distance_meters
        FROM 
            census.locations l
        WHERE 
            ST_DWithin(
                l.geometry::geography, 
                ST_SetSRID(ST_MakePoint(:longitude, :latitude), 4326)::geography, 
                :distance
            )
            {types_clause}
        ORDER BY 
            distance_meters
        LIMIT :limit
    """
    
    result = db.execute(query, query_params).fetchall()
    
    locations = []
    for row in result:
        location = {
            "location_id": row[0],
            "name": row[1],
            "type": row[2],
            "fips_code": row[3],
            "geometry": json.loads(row[4]) if row[4] else None,
            "distance_meters": float(row[5])
        }
        locations.append(location)
    
    # Cache the result
    cache.cache_query_result("nearby", params, locations)
    
    return locations

# Endpoint to find locations within a polygon
@app.post("/api/within", response_model=List[LocationResponse])
async def find_locations_within_polygon(
    polygon: GeoJSONPolygon,
    types: Optional[List[str]] = Query(None),
    limit: int = Query(100, ge=1, le=1000),
    db: Session = Depends(get_db)
):
    """Find locations within a given polygon boundary"""
    # Generate cache key for this query
    params = {
        "polygon": polygon.dict(),
        "types": types,
        "limit": limit
    }
    cached_result = cache.get_cached_query_result("within", params)
    if cached_result:
        return cached_result
    
    # Convert GeoJSON polygon to WKT
    polygon_obj = Polygon(polygon.coordinates[0])
    polygon_wkt = polygon_obj.wkt
    
    # Convert types list to SQL array if provided
    types_clause = ""
    query_params = {
        "polygon": polygon_wkt,
        "limit": limit
    }
    
    if types and len(types) > 0:
        types_clause = "AND l.type = ANY(:types)"
        query_params["types"] = types
    
    query = f"""
        SELECT 
            l.location_id, 
            l.name, 
            l.type, 
            l.fips_code, 
            ST_AsGeoJSON(l.geometry) as geometry_json
        FROM 
            census.locations l
        WHERE 
            ST_Intersects(
                l.geometry, 
                ST_GeomFromText(:polygon, 4326)
            )
            {types_clause}
        LIMIT :limit
    """
    
    result = db.execute(query, query_params).fetchall()
    
    locations = []
    for row in result:
        location = {
            "location_id": row[0],
            "name": row[1],
            "type": row[2],
            "fips_code": row[3],
            "geometry": json.loads(row[4]) if row[4] else None
        }
        locations.append(location)
    
    # Cache the result
    cache.cache_query_result("within", params, locations)
    
    return locations

# Endpoint to find containing regions (e.g., which county contains this point)
@app.post("/api/containing", response_model=List[LocationResponse])
async def find_containing_regions(
    point: Point,
    types: Optional[List[str]] = Query(None),
    db: Session = Depends(get_db)
):
    """Find regions that contain the given point"""
    # Generate cache key for this query
    params = {
        "longitude": point.longitude,
        "latitude": point.latitude,
        "types": types
    }
    cached_result = cache.get_cached_query_result("containing", params)
    if cached_result:
        return cached_result
    
    # Convert types list to SQL array if provided
    types_clause = ""
    query_params = {
        "longitude": point.longitude,
        "latitude": point.latitude
    }
    
    if types and len(types) > 0:
        types_clause = "AND l.type = ANY(:types)"
        query_params["types"] = types
    
    query = f"""
        SELECT 
            l.location_id, 
            l.name, 
            l.type, 
            l.fips_code, 
            ST_AsGeoJSON(l.geometry) as geometry_json
        FROM 
            census.locations l
        WHERE 
            ST_Contains(
                l.geometry, 
                ST_SetSRID(ST_MakePoint(:longitude, :latitude), 4326)
            )
            {types_clause}
        ORDER BY
            ST_Area(l.geometry::geography) ASC
    """
    
    result = db.execute(query, query_params).fetchall()
    
    locations = []
    for row in result:
        location = {
            "location_id": row[0],
            "name": row[1],
            "type": row[2],
            "fips_code": row[3],
            "geometry": json.loads(row[4]) if row[4] else None
        }
        locations.append(location)
    
    # Cache the result
    cache.cache_query_result("containing", params, locations)
    
    return locations

# Endpoint to get demographic data for a location
@app.get("/api/demographics/{location_id}", response_model=List[DemographicResponse])
async def get_demographics(
    location_id: str,
    category: Optional[str] = None,
    year: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Get demographic data for a specific location"""
    # Generate cache key based on parameters
    cache_key = f"demographics:{location_id}:{category or 'all'}:{year or 'all'}"
    cached_result = cache.get(cache_key)
    
    if cached_result:
        return cached_result
    
    query = """
        SELECT 
            location_id, 
            category, 
            raw_category, 
            year, 
            value
        FROM 
            census.demographics
        WHERE 
            location_id = :location_id
    """
    
    params = {"location_id": location_id}
    
    if category:
        query += " AND category = :category"
        params["category"] = category
    
    if year:
        query += " AND year = :year"
        params["year"] = year
    
    result = db.execute(query, params).fetchall()
    
    demographics = []
    for row in result:
        demographic = {
            "location_id": row[0],
            "category": row[1],
            "raw_category": row[2],
            "year": row[3],
            "value": row[4]
        }
        demographics.append(demographic)
    
    # Cache the result
    cache.set(cache_key, demographics)
    
    return demographics

# Endpoint to get time series data for a specific demographic category
@app.get("/api/timeseries/{location_id}/{category}", response_model=TimeSeriesResponse)
async def get_time_series(
    location_id: str,
    category: str,
    db: Session = Depends(get_db)
):
    """Get time series data for a specific demographic category and location"""
    # Check cache first
    cache_key = f"timeseries:{location_id}:{category}"
    cached_result = cache.get(cache_key)
    
    if cached_result:
        return cached_result
    
    # Get location name
    location_query = "SELECT name FROM census.locations WHERE location_id = :location_id"
    location_result = db.execute(location_query, {"location_id": location_id}).fetchone()
    
    if not location_result:
        raise HTTPException(status_code=404, detail="Location not found")
    
    location_name = location_result[0]
    
    # Get time series data
    query = """
        SELECT 
            year, 
            value
        FROM 
            census.demographics
        WHERE 
            location_id = :location_id
            AND category = :category
        ORDER BY 
            year
    """
    
    result = db.execute(query, {"location_id": location_id, "category": category}).fetchall()
    
    if not result:
        raise HTTPException(status_code=404, detail=f"No data found for category '{category}'")
    
    # Build time series
    values = {row[0]: row[1] for row in result}
    
    time_series = {
        "location_id": location_id,
        "name": location_name,
        "category": category,
        "values": values
    }
    
    # Cache the result
    cache.set(cache_key, time_series)
    
    return time_series

# Endpoint to compare demographic data across locations
@app.get("/api/compare/{category}", response_model=Dict[str, Dict[str, Any]])
async def compare_locations(
    category: str,
    location_ids: List[str] = Query(...),
    year: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Compare demographic data for multiple locations"""
    # Generate cache key based on parameters
    params_str = f"{category}:{'-'.join(sorted(location_ids))}:{year or 'latest'}"
    cache_key = f"compare:{params_str}"
    cached_result = cache.get(cache_key)
    
    if cached_result:
        return cached_result
    
    # Build a complex query to get the data efficiently
    year_condition = ""
    params = {"category": category, "location_ids": location_ids}
    
    if year:
        year_condition = "AND d.year = :year"
        params["year"] = year
    else:
        # If no year specified, get the latest available for each location
        year_condition = """
            AND d.year = (
                SELECT MAX(year) 
                FROM census.demographics 
                WHERE location_id = d.location_id AND category = d.category
            )
        """
    
    query = f"""
        SELECT 
            l.location_id, 
            l.name, 
            d.category, 
            d.year, 
            d.value
        FROM 
            census.demographics d
        JOIN 
            census.locations l ON d.location_id = l.location_id
        WHERE 
            d.category = :category
            AND d.location_id = ANY(:location_ids)
            {year_condition}
    """
    
    result = db.execute(query, params).fetchall()
    
    comparison = {}
    for row in result:
        location_id = row[0]
        location_name = row[1]
        category_name = row[2]
        year_value = row[3]
        value = row[4]
        
        comparison[location_id] = {
            "name": location_name,
            "category": category_name,
            "year": year_value,
            "value": value
        }
    
    # Cache the result
    cache.set(cache_key, comparison)
    
    return comparison

# Endpoint to get a bounding box that contains all locations of specified types
@app.get("/api/bounding-box", response_model=BoundingBox)
async def get_bounding_box(
    types: Optional[List[str]] = Query(None),
    db: Session = Depends(get_db)
):
    """Get a bounding box that contains all locations of specified types"""
    # Generate cache key based on parameters
    types_str = "-".join(sorted(types)) if types else "all"
    cache_key = f"bounding_box:{types_str}"
    cached_result = cache.get(cache_key)
    
    if cached_result:
        return cached_result
    
    # Build query
    types_clause = ""
    params = {}
    
    if types and len(types) > 0:
        types_clause = "WHERE type = ANY(:types)"
        params["types"] = types
    
    query = f"""
        SELECT 
            ST_XMin(ST_Extent(geometry)) as min_longitude,
            ST_YMin(ST_Extent(geometry)) as min_latitude,
            ST_XMax(ST_Extent(geometry)) as max_longitude,
            ST_YMax(ST_Extent(geometry)) as max_latitude
        FROM 
            census.locations
        {types_clause}
    """
    
    result = db.execute(query, params).fetchone()
    
    if not result or not all(result):
        # Default to continental US if no data
        bounding_box = {
            "min_longitude": -124.848974,
            "min_latitude": 24.396308,
            "max_longitude": -66.885444,
            "max_latitude": 49.384358
        }
    else:
        bounding_box = {
            "min_longitude": float(result[0]),
            "min_latitude": float(result[1]),
            "max_longitude": float(result[2]),
            "max_latitude": float(result[3])
        }
    
    # Cache the result
    cache.set(cache_key, bounding_box)
    
    return bounding_box

# Run the application
if __name__ == "__main__":
    import uvicorn
    
    # Get host and port from environment variables with defaults
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8000"))
    
    # Start the server
    uvicorn.run(app, host=host, port=port)