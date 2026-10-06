# MAP-01: Southbank building context

Run the local city demo using the [development guide](../development.md). Use the city scenario so tram, weather and development details are visible.

1. The map starts in 2D. Select **3D** to load the same-origin building asset and switch to a pitched view. The active button is dark; select it again to return to 2D.
2. Drag with the right mouse button to rotate, or use MapLibre's compass/zoom controls. Keyboard map navigation and the tram/development lists remain available. Reduced motion skips the camera transition and leaves playback paused.
3. Open **Layers** and toggle **Buildings (historical)**. This only changes rendering: the clock, area conditions, coverage and API request state stay the same.
4. Hover a building to inspect its historical structure ID, component base/top and capture date. Open **Map credits** for source, licence and modification information. The **Map display classes** legend explains observed, interpolated, modelled, simulated and illustrative elements; MAP-02/05 entries do not claim those layers are implemented.
5. Select a tram using its map marker or keyboard list. Existing warning areas and development markers remain selectable/inspectable through their established lists. Buildings are never matched to development records or counted as current events.

The layer retains whole Structure polygons intersecting Southbank. Dates are 2018–2023: recent construction may be absent. Grey transparent massing is captured visual context, not a live building feed. Other footprint types, terrain, external basemaps and 3D vehicle/particle animations are outside MAP-01.

If the building asset fails, city details and the base map remain usable; switch to 2D and back to retry. If WebGL is unavailable, use the map fallback and keyboard lists. Context loss removes map markers; when the browser restores the context, the map rebuilds with the latest city data. See [source and verification evidence](../evidence/map-01-building-massing.md).
