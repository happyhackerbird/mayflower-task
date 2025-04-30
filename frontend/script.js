document.addEventListener('DOMContentLoaded', () => {
    const addressInput = document.getElementById('address-input');
    const suggestionsContainer = document.getElementById('suggestions-container');
    const submitButton = document.getElementById('submit-button');
    const addressDisplay = document.getElementById('address-display');
    const poemDisplay = document.getElementById('poem-display');
    const errorDisplay = document.getElementById('error-display');

    // --- Configuration ---
    // IMPORTANT: Removed API key - Handled by backend proxy
    const backendApiUrl = 'http://127.0.0.1:8000/api/v1/addresses/'; // Your backend endpoint for addresses
    // CORRECTED: Use absolute URL for the backend proxy
    const backendAutocompleteProxyUrl = 'http://127.0.0.1:8000/api/v1/geo/autocomplete'; 
    let debounceTimeout; // For debouncing input
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
        clearTimeout(debounceTimeout);
        const query = addressInput.value;
        suggestionsContainer.innerHTML = ''; // Clear previous suggestions
        suggestionsContainer.style.display = 'none';
        selectedPlaceId = null; // Reset selection if user types again

        if (query.length < 3) {
            return; // Don't query for very short strings
        }

        debounceTimeout = setTimeout(async () => {
            // UPDATED: Call our backend proxy endpoint
            const url = `${backendAutocompleteProxyUrl}?query=${encodeURIComponent(query)}`;

            try {
                // UPDATED: Fetch from backend proxy URL
                const response = await fetch(url, { headers: { 'Accept': 'application/json' } }); 
                if (!response.ok) {
                    // Try to get error detail from backend response
                    let errorDetail = `Autocomplete failed: ${response.statusText}`;
                    try {
                        const errorData = await response.json();
                        errorDetail = errorData.detail || errorDetail;
                    } catch (e) { /* Ignore if response body is not JSON */ }
                    throw new Error(errorDetail);
                }
                const data = await response.json();
                // The backend returns the raw Geoapify response, so features are directly accessible
                displaySuggestions(data.features); 
            } catch (error) {
                console.error('Error fetching autocomplete via backend:', error);
                errorDisplay.textContent = `Autocomplete Error: ${error.message}`; // Show error to user
                suggestionsContainer.innerHTML = ''; // Clear any stale suggestions
                suggestionsContainer.style.display = 'none';
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
        let selectedProperties = null;

        // Check if a suggestion was clicked and retrieve its properties
        const selectedSuggestion = suggestionsContainer.querySelector(`div[data-place-id="${selectedPlaceId}"]`);
        if (selectedSuggestion && selectedSuggestion.dataset.properties) {
            try {
                selectedProperties = JSON.parse(selectedSuggestion.dataset.properties);
            } catch (e) {
                console.error("Failed to parse suggestion properties:", e);
                selectedProperties = null; // Fallback if parsing fails
            }
        }

        if (!inputText && !selectedProperties) { // Need either text or selection
            errorDisplay.textContent = 'Please enter an address or select a suggestion.';
            return;
        }

        try {
            // Step 1: Prepare data for our backend API (matching AddressCreate model)
            // Prioritize selected suggestion properties if available, otherwise parse inputText (basic split)
            let backendPayload = {};
            if (selectedProperties) {
                 console.log("Using selected suggestion properties:", selectedProperties); 
                backendPayload = {
                    street: selectedProperties.street || (selectedProperties.name || 'N/A'),
                    city: selectedProperties.city || 'N/A',
                    state: selectedProperties.state || 'N/A',
                    zip: selectedProperties.postcode || 'N/A',
                    country: selectedProperties.country || 'N/A',
                };
            } else {
                // Basic parsing of free-form text - the backend will standardize this anyway
                console.log("Using freeform text input:", inputText);
                const parts = inputText.split(',').map(p => p.trim());
                // This parsing is very naive, rely on backend geocoding primarily
                backendPayload = {
                    street: parts[0] || 'N/A', 
                    city: parts[1] || 'N/A',
                    state: parts[2] || 'N/A', // Might include zip here
                    zip: parts[3] || (parts[2] && parts[2].match(/\d{5}/) ? parts[2].match(/\d{5}/)[0] : 'N/A'), // Crude zip extraction
                    country: parts[parts.length - 1] || 'N/A'
                };
            }

            // Basic validation before sending
            if (backendPayload.city === 'N/A' || backendPayload.country === 'N/A') {
                 throw new Error('Could not determine city or country from input. Please be more specific or select a suggestion.');
            }

            console.log("Sending to backend:", backendPayload);

            // Step 2: Call our backend API (REMOVED direct Geoapify Search call)
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
                 const errorDetail = resultData.detail || `Backend error: ${backendResponse.statusText}`;
                 throw new Error(errorDetail);
            }

            // Step 3: Display results from backend
            addressDisplay.textContent = `Address (Standardized by Backend):
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