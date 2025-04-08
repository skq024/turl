#!/bin/bash
set -e

# Run PostgreSQL commands as the postgres user
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    -- Enable PostGIS extension
    CREATE EXTENSION IF NOT EXISTS postgis;
    CREATE EXTENSION IF NOT EXISTS postgis_topology;
    CREATE EXTENSION IF NOT EXISTS fuzzystrmatch;
    CREATE EXTENSION IF NOT EXISTS postgis_tiger_geocoder;

    -- Create schema for our census data
    CREATE SCHEMA IF NOT EXISTS census;

    -- Create locations table with geospatial support
    CREATE TABLE IF NOT EXISTS census.locations (
        location_id VARCHAR(100) PRIMARY KEY,
        name VARCHAR(255) NOT NULL,
        type VARCHAR(50) NOT NULL,
        fips_code VARCHAR(20),
        parent_location_id VARCHAR(100),
        url VARCHAR(500),
        scraped_at TIMESTAMP,
        geometry GEOMETRY(GEOMETRY, 4326),  -- Using WGS84 SRID: 4326
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    -- Create demographics table for storing time series data
    CREATE TABLE IF NOT EXISTS census.demographics (
        demographic_id SERIAL PRIMARY KEY,
        location_id VARCHAR(100) NOT NULL,
        category VARCHAR(100) NOT NULL,
        raw_category VARCHAR(255) NOT NULL,
        year VARCHAR(20) NOT NULL,
        value NUMERIC,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (location_id) REFERENCES census.locations(location_id) ON DELETE CASCADE
    );

    -- Create index for geospatial queries
    CREATE INDEX IF NOT EXISTS idx_locations_geometry ON census.locations USING GIST(geometry);

    -- Create indices for faster lookups
    CREATE INDEX IF NOT EXISTS idx_locations_type ON census.locations(type);
    CREATE INDEX IF NOT EXISTS idx_locations_fips ON census.locations(fips_code);
    CREATE INDEX IF NOT EXISTS idx_demographics_location ON census.demographics(location_id);
    CREATE INDEX IF NOT EXISTS idx_demographics_category ON census.demographics(category);
    CREATE INDEX IF NOT EXISTS idx_demographics_year ON census.demographics(year);

    -- Function to update timestamps
    CREATE OR REPLACE FUNCTION update_timestamp()
    RETURNS TRIGGER AS $$
    BEGIN
        NEW.updated_at = CURRENT_TIMESTAMP;
        RETURN NEW;
    END;
    $$ LANGUAGE plpgsql;

    -- Triggers to update timestamps
    DROP TRIGGER IF EXISTS update_locations_timestamp ON census.locations;
    CREATE TRIGGER update_locations_timestamp
    BEFORE UPDATE ON census.locations
    FOR EACH ROW EXECUTE FUNCTION update_timestamp();

    DROP TRIGGER IF EXISTS update_demographics_timestamp ON census.demographics;
    CREATE TRIGGER update_demographics_timestamp
    BEFORE UPDATE ON census.demographics
    FOR EACH ROW EXECUTE FUNCTION update_timestamp();

    -- Materialized view for commonly accessed demographic indicators
    CREATE MATERIALIZED VIEW IF NOT EXISTS census.common_indicators AS
    SELECT 
        l.location_id,
        l.name,
        l.type,
        l.fips_code,
        l.geometry,
        MAX(CASE WHEN d.category = 'population' AND d.year = (SELECT MAX(year) FROM census.demographics WHERE category = 'population' AND location_id = l.location_id) THEN d.value ELSE NULL END) AS population,
        MAX(CASE WHEN d.category = 'median_household_income' AND d.year = (SELECT MAX(year) FROM census.demographics WHERE category = 'median_household_income' AND location_id = l.location_id) THEN d.value ELSE NULL END) AS median_income,
        MAX(CASE WHEN d.category = 'persons_per_household' AND d.year = (SELECT MAX(year) FROM census.demographics WHERE category = 'persons_per_household' AND location_id = l.location_id) THEN d.value ELSE NULL END) AS persons_per_household,
        MAX(CASE WHEN d.category = 'median_home_value' AND d.year = (SELECT MAX(year) FROM census.demographics WHERE category = 'median_home_value' AND location_id = l.location_id) THEN d.value ELSE NULL END) AS median_home_value,
        MAX(CASE WHEN d.category = 'poverty_rate' AND d.year = (SELECT MAX(year) FROM census.demographics WHERE category = 'poverty_rate' AND location_id = l.location_id) THEN d.value ELSE NULL END) AS poverty_rate
    FROM 
        census.locations l
    LEFT JOIN 
        census.demographics d ON l.location_id = d.location_id
    GROUP BY 
        l.location_id, l.name, l.type, l.fips_code, l.geometry;

    -- Create index on the materialized view
    CREATE INDEX IF NOT EXISTS idx_common_indicators_location ON census.common_indicators(location_id);
    CREATE INDEX IF NOT EXISTS idx_common_indicators_geometry ON census.common_indicators USING GIST(geometry);

    -- Create function to find nearby locations
    CREATE OR REPLACE FUNCTION census.find_nearby_locations(
        point_geom GEOMETRY,
        max_distance_meters FLOAT,
        location_types TEXT[] DEFAULT NULL
    )
    RETURNS TABLE (
        location_id VARCHAR(100),
        name VARCHAR(255),
        type VARCHAR(50),
        distance_meters FLOAT,
        geometry GEOMETRY
    ) AS $$
    BEGIN
        RETURN QUERY
        SELECT 
            l.location_id,
            l.name,
            l.type,
            ST_Distance(l.geometry::geography, point_geom::geography) AS distance_meters,
            l.geometry
        FROM 
            census.locations l
        WHERE 
            (location_types IS NULL OR l.type = ANY(location_types))
            AND ST_DWithin(l.geometry::geography, point_geom::geography, max_distance_meters)
        ORDER BY 
            ST_Distance(l.geometry::geography, point_geom::geography);
    END;
    $$ LANGUAGE plpgsql;

    -- Create function to find locations within a polygon
    CREATE OR REPLACE FUNCTION census.find_locations_in_polygon(
        polygon_geom GEOMETRY,
        location_types TEXT[] DEFAULT NULL
    )
    RETURNS TABLE (
        location_id VARCHAR(100),
        name VARCHAR(255),
        type VARCHAR(50),
        geometry GEOMETRY
    ) AS $$
    BEGIN
        RETURN QUERY
        SELECT 
            l.location_id,
            l.name,
            l.type,
            l.geometry
        FROM 
            census.locations l
        WHERE 
            (location_types IS NULL OR l.type = ANY(location_types))
            AND ST_Intersects(l.geometry, polygon_geom);
    END;
    $$ LANGUAGE plpgsql;

    -- Create function to find containing regions for a point
    CREATE OR REPLACE FUNCTION census.find_containing_regions(
        point_geom GEOMETRY,
        location_types TEXT[] DEFAULT NULL
    )
    RETURNS TABLE (
        location_id VARCHAR(100),
        name VARCHAR(255),
        type VARCHAR(50),
        geometry GEOMETRY
    ) AS $$
    BEGIN
        RETURN QUERY
        SELECT 
            l.location_id,
            l.name,
            l.type,
            l.geometry
        FROM 
            census.locations l
        WHERE 
            (location_types IS NULL OR l.type = ANY(location_types))
            AND ST_Contains(l.geometry, point_geom)
        ORDER BY 
            ST_Area(l.geometry::geography) ASC;
    END;
    $$ LANGUAGE plpgsql;

    -- Grant privileges
    GRANT ALL PRIVILEGES ON SCHEMA census TO ${POSTGRES_USER};
    GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA census TO ${POSTGRES_USER};
    GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA census TO ${POSTGRES_USER};
    GRANT ALL PRIVILEGES ON ALL FUNCTIONS IN SCHEMA census TO ${POSTGRES_USER};
EOSQL