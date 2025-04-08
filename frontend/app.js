// app.js
// Entry point for the Geospatial Data Analytics application

// Configuration
const API_URL = 'http://localhost:8000/api';
const MAPBOX_TOKEN = 'pk.your_mapbox_token_here'; // Replace with your Mapbox token

// Application state
const state = {
    map: null,
    locationTypes: [],
    demographicCategories: [],
    years: [],
    selectedLocations: [],
    selectedCategory: null,
    selectedYear: null,
    currentView: 'map', // 'map' or 'chart'
    loading: false,
    timelineActive: false,
    timelineYear: null,
    timelineInterval: null,
    currentTimelineIndex: 0,
    mapLayers: [],
    drawMode: false,
    drawnPolygon: null,
    colorScale: null,
    drawPoints: [],
};

// Initialize the application
async function initApp() {
    renderAppStructure();
    showLoading(true);
    
    try {
        // Initialize Mapbox map
        initializeMap();
        
        // Load initial data
        await Promise.all([
            loadLocationTypes(),
            loadDemographicCategories(),
            loadYears(),
        ]);
        
        // Set up event listeners
        setupEventListeners();
        
        // Render controls with loaded data
        renderControls();
    } catch (error) {
        console.error('Error initializing application:', error);
        showError('Failed to initialize application. Please try refreshing the page.');
    } finally {
        showLoading(false);
    }
}

// Show loading indicator
function showLoading(show) {
    const loadingElement = document.getElementById('loading');
    if (loadingElement) {
        loadingElement.style.display = show ? 'flex' : 'none';
    }
    
    state.loading = show;
}

// Show error message
function showError(message) {
    alert(message); // Simple error display for now
}

// Load locations based on selected filters
async function loadLocations() {
    const locationType = document.getElementById('location-type').value;
    
    showLoading(true);
    
    try {
        // Build query parameters
        const params = new URLSearchParams();
        if (locationType) params.append('type', locationType);
        
        // Fetch locations from API
        const response = await fetch(`${API_URL}/locations?${params.toString()}`);
        if (!response.ok) throw new Error('Failed to load locations');
        
        const locations = await response.json();
        
        // Convert to GeoJSON
        const geoJsonData = {
            type: 'FeatureCollection',
            features: locations.map(locationToGeoJson)
        };
        
        // Update the map
        state.map.getSource('locations').setData(geoJsonData);
        
        // If a category is selected, update the choropleth
        if (state.selectedCategory && state.selectedYear) {
            updateChoropleth(state.selectedCategory, state.selectedYear);
        }
        
        // Fit the map to the data if needed
        if (locations.length > 0 && !locationType) {
            getBoundingBox().then(bbox => {
                state.map.fitBounds([
                    [bbox.min_longitude, bbox.min_latitude],
                    [bbox.max_longitude, bbox.max_latitude]
                ], { padding: 50 });
            });
        }
        
        console.log(`Loaded ${locations.length} locations`);
    } catch (error) {
        console.error('Error loading locations:', error);
        showError('Failed to load locations');
    } finally {
        showLoading(false);
    }
}

// Toggle between layers
function toggleLayers() {
    const button = document.getElementById('tool-layers');
    
    // Toggle active state
    button.classList.toggle('active');
    
    // Toggle visibility of layers
    const isActive = button.classList.contains('active');
    
    // Show/hide choropleth layer
    if (state.map.getLayer('choropleth')) {
        state.map.setLayoutProperty('choropleth', 'visibility', isActive ? 'visible' : 'none');
    }
}

// Toggle timeline view
function toggleTimeline() {
    const button = document.getElementById('tool-timeline');
    const timelineContainer = document.getElementById('timeline-container');
    
    if (!timelineContainer) return;
    
    // Toggle active state
    button.classList.toggle('active');
    
    // Toggle visibility
    const isActive = button.classList.contains('active');
    timelineContainer.style.display = isActive ? 'block' : 'none';
    
    // Initialize timeline if needed
    if (isActive && state.years.length > 0) {
        initializeTimeline();
    } else {
        // Stop any active timeline animation
        pauseTimeline();
    }
}

// Initialize timeline controls
function initializeTimeline() {
    const timelineSlider = document.getElementById('timeline-slider');
    const timelineYearDisplay = document.getElementById('timeline-year');
    
    if (!timelineSlider || !timelineYearDisplay) return;
    
    // Update slider range based on available years
    timelineSlider.min = 0;
    timelineSlider.max = state.years.length - 1;
    timelineSlider.value = state.currentTimelineIndex;
    
    // Update year display
    timelineYearDisplay.textContent = state.years[state.currentTimelineIndex];
    
    // Set the selected year
    state.timelineYear = state.years[state.currentTimelineIndex];
    
    // Update year select dropdown to match
    const yearSelect = document.getElementById('year');
    if (yearSelect) {
        yearSelect.value = state.timelineYear;
    }
}

// Handle timeline slider change
function handleTimelineSliderChange(e) {
    const index = parseInt(e.target.value, 10);
    if (index >= 0 && index < state.years.length) {
        state.currentTimelineIndex = index;
        const year = state.years[index];
        
        // Update the year display
        const timelineYearDisplay = document.getElementById('timeline-year');
        if (timelineYearDisplay) {
            timelineYearDisplay.textContent = year;
        }
        
        // Update state and visualization
        selectYear(year);
    }
}

// Play timeline animation
function playTimeline() {
    // Don't start if already playing
    if (state.timelineInterval) return;
    
    // Toggle play/pause buttons
    document.getElementById('timeline-play').style.display = 'none';
    document.getElementById('timeline-pause').style.display = 'inline-block';
    
    // Start interval
    state.timelineInterval = setInterval(() => {
        // Advance to next year
        nextTimelineYear();
        
        // If we reached the end, stop playback
        if (state.currentTimelineIndex >= state.years.length - 1) {
            pauseTimeline();
        }
    }, 1500); // Change year every 1.5 seconds
}

// Pause timeline animation
function pauseTimeline() {
    if (state.timelineInterval) {
        clearInterval(state.timelineInterval);
        state.timelineInterval = null;
    }
    
    // Toggle play/pause buttons
    document.getElementById('timeline-play').style.display = 'inline-block';
    document.getElementById('timeline-pause').style.display = 'none';
}

// Go to next year in timeline
function nextTimelineYear() {
    if (state.currentTimelineIndex < state.years.length - 1) {
        state.currentTimelineIndex++;
        const year = state.years[state.currentTimelineIndex];
        
        // Update slider position
        const timelineSlider = document.getElementById('timeline-slider');
        if (timelineSlider) {
            timelineSlider.value = state.currentTimelineIndex;
        }
        
        // Update the year display
        const timelineYearDisplay = document.getElementById('timeline-year');
        if (timelineYearDisplay) {
            timelineYearDisplay.textContent = year;
        }
        
        // Update state and visualization
        selectYear(year);
    }
}

// Go to previous year in timeline
function prevTimelineYear() {
    if (state.currentTimelineIndex > 0) {
        state.currentTimelineIndex--;
        const year = state.years[state.currentTimelineIndex];
        
        // Update slider position
        const timelineSlider = document.getElementById('timeline-slider');
        if (timelineSlider) {
            timelineSlider.value = state.currentTimelineIndex;
        }
        
        // Update the year display
        const timelineYearDisplay = document.getElementById('timeline-year');
        if (timelineYearDisplay) {
            timelineYearDisplay.textContent = year;
        }
        
        // Update state and visualization
        selectYear(year);
    }
}

// Toggle draw mode
function toggleDrawMode() {
    const button = document.getElementById('tool-draw');
    
    // Toggle active state
    button.classList.toggle('active');
    
    // Toggle draw mode
    state.drawMode = button.classList.contains('active');
    
    // Change cursor
    if (state.map) {
        state.map.getCanvas().style.cursor = state.drawMode ? 'crosshair' : '';
    }
    
    // Clear existing drawn area if deactivating
    if (!state.drawMode) {
        clearDrawing();
    } else {
        // Initialize the drawing state
        state.drawPoints = [];
        
        // Update draw button text
        const drawButton = document.getElementById('draw-button');
        if (drawButton) {
            drawButton.innerHTML = '<i class="fas fa-times"></i> Cancel Drawing';
        }
    }
}

// Handle draw clicks
function handleDrawClick(e) {
    // Add point to drawing
    state.drawPoints.push([e.lngLat.lng, e.lngLat.lat]);
    
    // Update the drawing on the map
    updateDrawing();
    
    // If we have at least 3 points, enable completing the polygon
    if (state.drawPoints.length >= 3) {
        // Add "complete" button if it doesn't exist
        if (!document.getElementById('complete-polygon')) {
            const drawButton = document.getElementById('draw-button');
            if (drawButton) {
                drawButton.insertAdjacentHTML('afterend', `
                    <button id="complete-polygon" class="mt-10" onclick="completePolygon()">
                        <i class="fas fa-check"></i> Complete Polygon
                    </button>
                `);
            }
        }
    }
}

// Update drawing on the map
function updateDrawing() {
    if (!state.map || !state.drawPoints.length) return;
    
    // Create features for the draw points
    const pointFeatures = state.drawPoints.map(point => ({
        type: 'Feature',
        geometry: {
            type: 'Point',
            coordinates: point
        },
        properties: {}
    }));
    
    // Create a line feature if there are at least 2 points
    let lineFeatures = [];
    if (state.drawPoints.length >= 2) {
        lineFeatures.push({
            type: 'Feature',
            geometry: {
                type: 'LineString',
                coordinates: [...state.drawPoints]
            },
            properties: {}
        });
    }
    
    // Create a polygon feature if there are at least 3 points
    let polygonFeatures = [];
    if (state.drawPoints.length >= 3) {
        // Close the polygon by duplicating the first point
        const polygonCoords = [...state.drawPoints, state.drawPoints[0]];
        
        polygonFeatures.push({
            type: 'Feature',
            geometry: {
                type: 'Polygon',
                coordinates: [polygonCoords]
            },
            properties: {}
        });
    }
    
    // Update the draw-area source
    state.map.getSource('drawn-area').setData({
        type: 'FeatureCollection',
        features: [...pointFeatures, ...lineFeatures, ...polygonFeatures]
    });
}

// Complete the polygon drawing
function completePolygon() {
    if (state.drawPoints.length < 3) return;
    
    // Create the final polygon
    const polygonCoords = [...state.drawPoints, state.drawPoints[0]];
    state.drawnPolygon = {
        type: 'Polygon',
        coordinates: [polygonCoords]
    };
    
    // Exit draw mode
    toggleDrawMode();
    
    // Query locations within this polygon
    withinPolygon();
    
    // Remove the complete button
    const completeButton = document.getElementById('complete-polygon');
    if (completeButton) {
        completeButton.remove();
    }
}

// Clear the drawing
function clearDrawing() {
    state.drawPoints = [];
    state.drawnPolygon = null;
    
    // Clear the draw-area source
    if (state.map) {
        state.map.getSource('drawn-area').setData({
            type: 'FeatureCollection',
            features: []
        });
    }
    
    // Update draw button text
    const drawButton = document.getElementById('draw-button');
    if (drawButton) {
        drawButton.innerHTML = '<i class="fas fa-draw-polygon"></i> Draw Area';
    }
    
    // Remove the complete button
    const completeButton = document.getElementById('complete-polygon');
    if (completeButton) {
        completeButton.remove();
    }
}

// Find locations within the drawn polygon
async function withinPolygon() {
    if (!state.map || !state.drawnPolygon) return;
    
    const locationType = document.getElementById('location-type').value;
    
    showLoading(true);
    
    try {
        // Prepare request body
        const requestBody = {
            type: 'Polygon',
            coordinates: state.drawnPolygon.coordinates
        };
        
        // Prepare URL with query parameters
        const params = new URLSearchParams();
        if (locationType) params.append('types', locationType);
        
        // Make API request
        const response = await fetch(`${API_URL}/within?${params.toString()}`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(requestBody)
        });
        
        if (!response.ok) throw new Error('Failed to find locations within polygon');
        
        const locationsWithin = await response.json();
        
        // Update the map with results
        displayPolygonResults(locationsWithin);
        
        console.log(`Found ${locationsWithin.length} locations within polygon`);
    } catch (error) {
        console.error('Error finding locations within polygon:', error);
        showError('Failed to find locations within polygon');
    } finally {
        showLoading(false);
    }
}

// Display polygon query results
function displayPolygonResults(locations) {
    // Convert locations to GeoJSON features
    const features = locations.map(location => {
        // Convert geometry if needed
        const geometry = typeof location.geometry === 'string'
            ? JSON.parse(location.geometry)
            : location.geometry;
        
        return {
            type: 'Feature',
            geometry: geometry,
            properties: {
                location_id: location.location_id,
                name: location.name,
                type: location.type,
                fips_code: location.fips_code
            }
        };
    });
    
    // Update selected locations
    const selectedLocationsSource = state.map.getSource('selected-locations');
    if (selectedLocationsSource) {
        selectedLocationsSource.setData({
            type: 'FeatureCollection',
            features: features
        });
    }
    
    // Fit map to show all results plus the polygon
    const bounds = new mapboxgl.LngLatBounds();
    
    // Include the polygon in the bounds
    state.drawnPolygon.coordinates[0].forEach(coord => {
        bounds.extend(coord);
    });
    
    // Include all features in the bounds
    features.forEach(feature => {
        if (feature.geometry.type === 'Point') {
            bounds.extend(feature.geometry.coordinates);
        } else if (feature.geometry.type === 'Polygon') {
            feature.geometry.coordinates[0].forEach(coord => {
                bounds.extend(coord);
            });
        } else if (feature.geometry.type === 'MultiPolygon') {
            feature.geometry.coordinates.forEach(polygon => {
                polygon[0].forEach(coord => {
                    bounds.extend(coord);
                });
            });
        }
    });
    
    // Fit the map to the bounds
    state.map.fitBounds(bounds, { padding: 50 });
    
    // Update data panel
    const dataPanel = document.getElementById('data-panel');
    dataPanel.style.display = 'block';
    
    document.getElementById('data-panel-title').textContent = 'Locations Within Polygon';
    
    const dataContent = document.getElementById('data-content');
    
    if (features.length === 0) {
        dataContent.innerHTML = '<p class="data-empty">No locations found within the drawn polygon</p>';
        return;
    }
    
    dataContent.innerHTML = `
        <table class="data-table">
            <thead>
                <tr>
                    <th>Name</th>
                    <th>Type</th>
                    <th>FIPS Code</th>
                </tr>
            </thead>
            <tbody>
                ${features.map(feature => `
                    <tr>
                        <td>
                            <a href="#" onclick="viewDemographics('${feature.properties.location_id}'); return false;">
                                ${feature.properties.name}
                            </a>
                        </td>
                        <td>${feature.properties.type}</td>
                        <td>${feature.properties.fips_code || 'N/A'}</td>
                    </tr>
                `).join('')}
            </tbody>
        </table>
    `;
}

// Reset map view
function resetMapView() {
    if (!state.map) return;
    
    // Clear any selections
    state.selectedLocations = [];
    state.map.getSource('selected-locations').setData({
        type: 'FeatureCollection',
        features: []
    });
    
    // Clear any drawings
    clearDrawing();
    
    // Reset the view to continental US
    state.map.flyTo({
        center: [-98.5795, 39.8283], // Center of the US
        zoom: 3,
        duration: 1500
    });
    
    // Hide data panel
    const dataPanel = document.getElementById('data-panel');
    if (dataPanel) {
        dataPanel.style.display = 'none';
    }
}

// Initialize the application when the DOM is ready
document.addEventListener('DOMContentLoaded', initApp);