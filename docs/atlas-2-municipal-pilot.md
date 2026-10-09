# Supervised pilot assessment

`/pilot` loads actual city/controller summaries and calculates annual person-hours from paired simulated delay differences × assumed daily vehicles × assumed persons/vehicle × assumed days / 3,600. Projected value multiplies assumed person-hour value. Compute expense is an input; field integration, equipment, maintenance and procurement are excluded and must be budgeted separately. Negative simulated outcomes produce negative benefits. JSON export and browser print provide an assessment with evidence, assumptions and requirements.

The Python `POST /api/operations/pilot` independently validates matching networks, routes, scenarios, horizons and seed coverage before computing projections. These are uncalibrated exploratory simulation projections, not verified municipal savings. City models are not validated merely because roads came from OSM. No field ROI or emissions-reduction claim is made.

Before an agency pilot: secure source-use approval; acquire independent counts/turns/speeds; survey signal timings, pedestrian clearance and conflicts; calibrate on training observations and validate on an independent holdout; test incidents/outages, transit, emergency priority and equity; establish operator identity, retention, monitoring, procurement, hardware certification and a controlled shadow study. Roadway actuation is unavailable.

Authenticated approval/rejection/rollback endpoints store advisory audit events for known completed experiments. Those events do not alter municipal signal hardware. A signed emergency request validator is a primitive, not completed emergency integration.
