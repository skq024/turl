# Geospatial Data Mining, Visualization and Analytics

A comprehensive geospatial analytics system that extracts, visualizes, and analyzes US Census demographic data with interactive mapping capabilities.

## Features

- **Data Mining**: Scrapes US Census QuickFacts data for cities, states, counties, towns, and zip codes
- **Geospatial Visualization**: Interactive map visualization with Mapbox
- **Demographic Analysis**: View and compare demographic data across locations and time periods  
- **Geospatial Queries**: Find nearby locations, locations within polygons, and containing regions
- **Time Series Analysis**: Visualize how demographics change over time

## System Components

1. **Scraper**: Python pipeline to extract census data
2. **Database**: PostgreSQL with PostGIS for geospatial data storage
3. **Cache**: Redis for high-performance data access
4. **Backend API**: FastAPI application for geospatial queries
5. **Frontend**: Interactive map and data visualization interface

## Prerequisites

- Docker and Docker Compose
- Mapbox API key (for map visualization)

## Getting Started

### 1. Clone the repository

```bash
git clone https://github.com/yourusername/geospatial-analytics.git
cd geospatial-analytics
```

### 2. Configure environment variables

Copy the sample environment file and update with your settings:

```bash
cp .env.example .env
```

Edit the `.env` file to set your Mapbox API key and any other custom configuration.

### 3. Start the services

```bash
docker-compose up -d
```

This will start the PostgreSQL, Redis, backend, and frontend services.

### 4. Run the data scraper

```bash
docker-compose run --rm scraper
```

This will scrape the Census QuickFacts data and load it into the database.

### 5. Access the application

Open your web browser and navigate to:

```
http://localhost:80
```

## API Endpoints

The backend API provides the following endpoints:

- `GET /api/locations` - Get locations with optional filtering
- `GET /api/location-types` - Get all available location types
- `GET /api/demographic-categories` - Get all available demographic categories
- `GET /api/years` - Get all available years in the dataset
- `GET /api/locations/{location_id}` - Get details for a specific location
- `POST /api/nearby` - Find locations near a specified point
- `POST /api/within` - Find locations within a polygon
- `POST /api/containing` - Find regions containing a point
- `GET /api/demographics/{location_id}` - Get demographic data for a location
- `GET /api/timeseries/{location_id}/{category}` - Get time series data for a specific category
- `GET /api/compare/{category}` - Compare demographic data across locations
- `GET /api/bounding-box` - Get bounding box for locations

## Project Structure

```
geospatial-analytics/
├── backend/                 # FastAPI backend application
│   ├── app.py               # Main application file
│   ├── redis_cache.py       # Redis caching module
│   ├── requirements.txt     # Python dependencies
│   └── Dockerfile           # Backend container definition
├── frontend/                # Web frontend
│   ├── index.html           # Main HTML file
│   ├── app.js               # JavaScript application
│   ├── styles.css           # CSS styles
│   ├── nginx.conf           # Nginx configuration
│   └── Dockerfile           # Frontend container definition
├── scraper/                 # Data scraping pipeline
│   ├── census_scraper.py    # Census QuickFacts scraper
│   ├── data_processor.py    # Data processor and loader
│   ├── requirements.txt     # Python dependencies
│   └── Dockerfile           # Scraper container definition
├── init-scripts/            # Database initialization scripts
│   └── init-db.sh           # PostgreSQL setup script
├── docker-compose.yml       # Service orchestration configuration
├── .env.example             # Example environment variables
└── README.md                # This file
```

## Development

### Local Development Setup

For local development without Docker:

1. Set up a local PostgreSQL database with PostGIS extension
2. Install Redis locally
3. Set up Python virtual environments for the backend and scraper
4. Install dependencies from requirements.txt files
5. Run the backend using uvicorn
6. Serve the frontend using a local web server

### Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Acknowledgments

- US Census Bureau for providing the QuickFacts data
- Mapbox for the mapping visualization capabilities
- PostGIS for powerful geospatial database functionality