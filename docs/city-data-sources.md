# Official city observations and data-use register

Validated by `python scripts/check_city_sources.py --perception --samples 2`; actual responses and aggregate detections are in `artifacts/cities/source-health.json`. Access at one time does not guarantee future availability or establish every camera's health.

| City | Official catalog | Catalog cameras in this check | Sample image retrieval |
|---|---|---:|---|
| Toronto | [City ArcGIS layer](https://gis.toronto.ca/arcgis/rest/services/cot_geospatial2/FeatureServer/3) | 336 | 2/2 JPEGs |
| London | [TfL API](https://api.tfl.gov.uk/Place/Type/JamCam) | 890 | 2/2 JPEGs |
| Seattle | [SDOT traveler map API](https://web.seattle.gov/Travelers/api/Map/Data?zoomId=13&type=2) | 393 SDOT cameras | 2/2 JPEGs |
| Austin | [Official CCTV catalog](https://data.austintexas.gov/Transportation-and-Mobility/Traffic-Cameras/b4k4-adkb) | 1,008 | 2/2 JPEGs; separately tested desired camera 670 returned 403 |
| Calgary | [Official traffic cameras](https://data.calgary.ca/d/k7p9-kppz) | 216 | 2/2 JPEGs over HTTPS |

Toronto's `IMAGEURL`, Austin's `screenshot_address`, Calgary's `camera_url`, TfL additional properties, and SDOT's published image filenames are normalized independently. Seattle's API query must retain `zoomId` and `type`; a test protects against HTTP-client query replacement. A 403 is reported, never bypassed. TfL clip URLs are discovered but not processed as continuous streams. No Montréal or NYC integration is claimed.

**Timestamp semantics:** retrieval time is known. HTTP Last-Modified is a source freshness proxy, not verified camera capture time. TfL property modification and Austin catalog update times are metadata times, not image times. Captured-at remains null. Check-time proxy age and stale/future-clock flags are explicit. Exact refresh behavior has not been established by a prolonged polling study. Cached artifacts are labeled recorded source checks.

**Rights:** city-specific terms links, attribution, source hosts and image redistribution restrictions are in `docs/cities.json`. Toronto metadata uses its open-government licence; London requires TfL transport-data terms, attribution and production developer registration. [TfL's camera guidance](https://tfl.gov.uk/info-for/open-data-users/our-open-data) specifies two-minute publication/display freshness and fifteen-minute maximum display before update. Optional `ATLAS_TFL_APP_KEY` stays server-side and is never emitted. Seattle/Austin/Calgary imagery redistribution rights are not presumed from public access; operational approval and current terms review remain pilot prerequisites. This increment redistributes **no camera images or clips**.

Local inference uses pretrained YOLO11n on permitted public image samples, retaining counts, model scores, dimensions, blur/brightness proxies and content digests. No identity recognition or plate recognition is implemented. No speed, precise queue, flow, turn count or persistent track is inferred from these stills. Independent five-city annotations, night/weather accuracy and camera calibration remain missing; historical UA-DETRAC accuracy is not assigned to these feeds.

**OSM:** small source maps and converted networks are separately packaged under ODbL with attribution. They establish road geometry, not municipal signal plans or traffic demand. Pinned `.gz` inputs can be restored without re-downloading. Regeneration from current OSM is a new network version.
