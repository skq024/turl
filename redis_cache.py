# redis_cache.py
import redis
import json
import logging
import hashlib
from datetime import timedelta
from typing import Dict, List, Any, Optional, Union

class GeoCache:
    """Redis-based caching system for geospatial data"""
    
    def __init__(self, host='localhost', port=6379, db=0, password=None, ttl_seconds=3600):
        """Initialize the caching system
        
        Args:
            host (str): Redis host
            port (int): Redis port
            db (int): Redis database number
            password (str, optional): Redis password
            ttl_seconds (int): Default time-to-live for cache entries in seconds
        """
        self.redis = redis.Redis(
            host=host,
            port=port,
            db=db,
            password=password,
            decode_responses=True  # Automatically decode responses
        )
        self.ttl = ttl_seconds
        self.logger = logging.getLogger(__name__)
    
    def generate_key(self, prefix: str, params: Dict[str, Any]) -> str:
        """Generate a consistent cache key based on prefix and parameters
        
        Args:
            prefix (str): Key prefix (e.g., 'nearby', 'polygon')
            params (dict): Parameters that define the query
            
        Returns:
            str: The generated cache key
        """
        # Sort params for consistent hashing regardless of order
        param_str = json.dumps(params, sort_keys=True)
        
        # Generate MD5 hash of the parameters
        param_hash = hashlib.md5(param_str.encode()).hexdigest()
        
        # Combine prefix and hash
        return f"geo:{prefix}:{param_hash}"
    
    def set(self, key: str, data: Any, ttl: Optional[int] = None) -> bool:
        """Store data in cache with expiration
        
        Args:
            key (str): Cache key
            data (Any): Data to store (will be JSON serialized)
            ttl (int, optional): Time-to-live in seconds. Uses default if None.
            
        Returns:
            bool: Success status
        """
        try:
            serialized = json.dumps(data)
            expiration = ttl if ttl is not None else self.ttl
            
            success = self.redis.setex(key, expiration, serialized)
            if success:
                self.logger.debug(f"Cached data with key {key}")
            else:
                self.logger.warning(f"Failed to cache data with key {key}")
                
            return success
        except Exception as e:
            self.logger.error(f"Error caching data: {str(e)}")
            return False
    
    def get(self, key: str) -> Optional[Any]:
        """Retrieve data from cache
        
        Args:
            key (str): Cache key
            
        Returns:
            Any: The cached data or None if not found
        """
        try:
            data = self.redis.get(key)
            if data:
                self.logger.debug(f"Cache hit for key {key}")
                return json.loads(data)
            else:
                self.logger.debug(f"Cache miss for key {key}")
                return None
        except Exception as e:
            self.logger.error(f"Error retrieving cached data: {str(e)}")
            return None
    
    def delete(self, key: str) -> bool:
        """Remove data from cache
        
        Args:
            key (str): Cache key
            
        Returns:
            bool: Success status
        """
        try:
            result = self.redis.delete(key)
            if result:
                self.logger.debug(f"Deleted cache key {key}")
            return bool(result)
        except Exception as e:
            self.logger.error(f"Error deleting cached data: {str(e)}")
            return False
    
    def invalidate_by_prefix(self, prefix: str) -> int:
        """Invalidate all cache entries with a given prefix
        
        Args:
            prefix (str): The prefix to match
            
        Returns:
            int: Number of keys deleted
        """
        try:
            pattern = f"geo:{prefix}:*"
            keys = self.redis.keys(pattern)
            
            if not keys:
                return 0
                
            deleted = self.redis.delete(*keys)
            self.logger.info(f"Invalidated {deleted} cache entries with prefix {prefix}")
            return deleted
        except Exception as e:
            self.logger.error(f"Error invalidating cache: {str(e)}")
            return 0
    
    def store_geospatial_point(self, name: str, longitude: float, latitude: float) -> bool:
        """Store a geospatial point in Redis
        
        Args:
            name (str): Point identifier
            longitude (float): Longitude
            latitude (float): Latitude
            
        Returns:
            bool: Success status
        """
        try:
            result = self.redis.geoadd("geo:points", longitude, latitude, name)
            self.logger.debug(f"Added geospatial point {name} at ({longitude}, {latitude})")
            return bool(result)
        except Exception as e:
            self.logger.error(f"Error storing geospatial point: {str(e)}")
            return False
    
    def find_nearby_points(self, longitude: float, latitude: float, radius_km: float, 
                          count: Optional[int] = None) -> List[Dict[str, Any]]:
        """Find geospatial points within a radius
        
        Args:
            longitude (float): Center point longitude
            latitude (float): Center point latitude
            radius_km (float): Radius in kilometers
            count (int, optional): Maximum number of results
            
        Returns:
            List[Dict]: List of nearby points with distance
        """
        try:
            args = ["geo:points", longitude, latitude, radius_km, "km"]
            if count:
                args.extend(["COUNT", count])
                
            # Add WITHDIST to get distances
            args.append("WITHDIST")
            
            results = self.redis.georadius(*args)
            
            # Format the results
            nearby_points = []
            for result in results:
                name, distance = result
                nearby_points.append({
                    "name": name,
                    "distance_km": float(distance)
                })
                
            return nearby_points
        except Exception as e:
            self.logger.error(f"Error finding nearby points: {str(e)}")
            return []
    
    def store_location_boundaries(self, location_id: str, boundary_data: Dict) -> bool:
        """Store location boundary data in Redis
        
        Args:
            location_id (str): Location identifier
            boundary_data (dict): GeoJSON boundary data
            
        Returns:
            bool: Success status
        """
        key = f"geo:boundary:{location_id}"
        return self.set(key, boundary_data)
    
    def get_location_boundaries(self, location_id: str) -> Optional[Dict]:
        """Retrieve location boundary data from Redis
        
        Args:
            location_id (str): Location identifier
            
        Returns:
            Optional[Dict]: GeoJSON boundary data or None if not found
        """
        key = f"geo:boundary:{location_id}"
        return self.get(key)
    
    def store_demographic_data(self, location_id: str, data: Dict, category: Optional[str] = None) -> bool:
        """Store demographic data in Redis
        
        Args:
            location_id (str): Location identifier
            data (dict): Demographic data
            category (str, optional): Specific category if storing by category
            
        Returns:
            bool: Success status
        """
        if category:
            key = f"geo:demographics:{location_id}:{category}"
        else:
            key = f"geo:demographics:{location_id}"
            
        return self.set(key, data)
    
    def get_demographic_data(self, location_id: str, category: Optional[str] = None) -> Optional[Dict]:
        """Retrieve demographic data from Redis
        
        Args:
            location_id (str): Location identifier
            category (str, optional): Specific category if retrieving by category
            
        Returns:
            Optional[Dict]: Demographic data or None if not found
        """
        if category:
            key = f"geo:demographics:{location_id}:{category}"
        else:
            key = f"geo:demographics:{location_id}"
            
        return self.get(key)
    
    def cache_query_result(self, query_type: str, params: Dict, result: Any, ttl: Optional[int] = None) -> bool:
        """Cache the result of a geospatial query
        
        Args:
            query_type (str): Type of query (e.g., 'nearby', 'polygon')
            params (dict): Query parameters
            result (Any): Query result to cache
            ttl (int, optional): Time-to-live in seconds
            
        Returns:
            bool: Success status
        """
        key = self.generate_key(query_type, params)
        return self.set(key, result, ttl)
    
    def get_cached_query_result(self, query_type: str, params: Dict) -> Optional[Any]:
        """Retrieve the cached result of a geospatial query
        
        Args:
            query_type (str): Type of query (e.g., 'nearby', 'polygon')
            params (dict): Query parameters
            
        Returns:
            Optional[Any]: Cached result or None if not found
        """
        key = self.generate_key(query_type, params)
        return self.get(key)
    
    def health_check(self) -> bool:
        """Check if Redis is accessible
        
        Returns:
            bool: True if Redis is working, False otherwise
        """
        try:
            return self.redis.ping()
        except Exception as e:
            self.logger.error(f"Redis health check failed: {str(e)}")
            return False