document.addEventListener('DOMContentLoaded', () => {
    const addressInput = document.getElementById('address-input');
    const suggestionsContainer = document.getElementById('suggestions-container');
    const submitButton = document.getElementById('submit-button');
    const addressDisplay = document.getElementById('address-display');
    const poemDisplay = document.getElementById('poem-display');
    const errorDisplay = document.getElementById('error-display');

    // --- Configuration ---
    // IMPORTANT: Replace with your actual Geoapify API Key
    const geoapifyApiKey = 'daa3eefc82f2469aa101ae6b2d3e7dd9'; 
    const backendApiUrl = 'http://127.0.0.1:8000/api/v1/addresses/'; // Your backend endpoint
    let debounceTimer; // For autocomplete debouncing
    let selectedPlaceId = null; // Store place_id from suggestion

    // --- Clear Results/Errors ---
    function clearResults() {
        addressDisplay.textContent = '';
        poemDisplay.textContent = '';
        errorDisplay.textContent = '';
        suggestionsContainer.innerHTML = '';
        suggestionsContainer.style.display = 'none';
        selectedPlaceId = null;
    }

    // --- Geoapify Autocomplete ---
    addressInput.addEventListener('input', () => {
        clearTimeout(debounceTimer);
        const query = addressInput.value;
        suggestionsContainer.innerHTML = ''; // Clear previous suggestions
        suggestionsContainer.style.display = 'none';
        selectedPlaceId = null; // Reset selection if user types again

        if (query.length < 3) {
            return; // Don't query for very short strings
        }

        debounceTimer = setTimeout(async () => {
            const autocompleteUrl = `https://api.geoapify.com/v1/geocode/autocomplete?text=${encodeURIComponent(query)}&apiKey=${geoapifyApiKey}`;

            try {
                const response = await fetch(autocompleteUrl, { headers: { 'Accept': 'application/json' } });
                if (!response.ok) {
                    throw new Error(`Geoapify Autocomplete error: ${response.statusText}`);
                }
                const data = await response.json();
                displaySuggestions(data.features);
            } catch (error) {
                console.error('Error fetching autocomplete:', error);
                // Optionally show error to user
            }
        }, 300); // Debounce time in ms
    });

    function displaySuggestions(features) {
        suggestionsContainer.innerHTML = '';
        if (!features || features.length === 0) {
            suggestionsContainer.style.display = 'none';
            return;
        }

        features.forEach(feature => {
            const div = document.createElement('div');
            div.textContent = feature.properties.formatted;
            // Store place_id and full properties needed for geocoding
            div.dataset.placeId = feature.properties.place_id; 
            div.dataset.properties = JSON.stringify(feature.properties); // Store all properties
            div.addEventListener('click', () => {
                addressInput.value = feature.properties.formatted;
                selectedPlaceId = feature.properties.place_id;
                suggestionsContainer.innerHTML = '';
                suggestionsContainer.style.display = 'none';
            });
            suggestionsContainer.appendChild(div);
        });
        suggestionsContainer.style.display = 'block';
    }

    // Hide suggestions if clicked outside
    document.addEventListener('click', (event) => {
        if (!addressInput.contains(event.target) && !suggestionsContainer.contains(event.target)) {
            suggestionsContainer.style.display = 'none';
        }
    });

    // --- Submit Button Logic ---
    submitButton.addEventListener('click', async () => {
        clearResults();
        const inputText = addressInput.value;

        if (!inputText) {
            errorDisplay.textContent = 'Please enter an address.';
            return;
        }

        // If a suggestion was selected, use its place_id for precise geocoding
        // Otherwise, use the freeform text
        const geocodeUrl = selectedPlaceId
            ? `https://api.geoapify.com/v1/geocode/search?place_id=${selectedPlaceId}&apiKey=${geoapifyApiKey}`
            : `https://api.geoapify.com/v1/geocode/search?text=${encodeURIComponent(inputText)}&apiKey=${geoapifyApiKey}&limit=1`;

        console.log("Geocoding URL:", geocodeUrl); // Debugging

        try {
            // Step 1: Geocode the selected suggestion or freeform text
            const geoResponse = await fetch(geocodeUrl, { headers: { 'Accept': 'application/json' } });
            if (!geoResponse.ok) {
                throw new Error(`Geoapify Geocode error: ${geoResponse.statusText}`);
            }
            const geoData = await geoResponse.json();

            if (!geoData.features || geoData.features.length === 0) {
                throw new Error('Could not find location details for the address.');
            }

            const properties = geoData.features[0].properties;

            // Step 2: Prepare data for our backend API (matching AddressCreate model)
            const backendPayload = {
                street: properties.street || (properties.name || 'N/A'), // Handle missing street
                city: properties.city || 'N/A',
                state: properties.state || 'N/A',
                zip: properties.postcode || 'N/A',
                country: properties.country || 'N/A',
            };

            // Basic validation: Ensure core fields are present
            if (backendPayload.city === 'N/A' || backendPayload.country === 'N/A') {
                 throw new Error('Geocoding result missing essential city or country information.');
            }

            console.log("Sending to backend:", backendPayload); // Debugging

            // Step 3: Call our backend API
            const backendResponse = await fetch(backendApiUrl, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Accept': 'application/json'
                },
                body: JSON.stringify(backendPayload)
            });

            const resultData = await backendResponse.json();

            if (!backendResponse.ok) {
                 // Use error detail from backend if available
                 const errorDetail = resultData.detail || `Backend error: ${backendResponse.statusText}`;
                 throw new Error(errorDetail);
            }

            // Display results
            addressDisplay.textContent = `Address:
Street: ${resultData.street}
City: ${resultData.city}
State: ${resultData.state}
Zip: ${resultData.zip}
Country: ${resultData.country}
Location Key: ${resultData.location_key}`;
            poemDisplay.textContent = resultData.poem_text || 'No poem available.';

        } catch (error) {
            console.error('Error during submission:', error);
            errorDisplay.textContent = `Error: ${error.message}`;
        }
    });
}); 