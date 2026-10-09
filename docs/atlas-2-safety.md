# Modeled safety, permissions and limits

The optimizer cannot set lamps directly in `network_v2.py`. `SafetyGate` owns valid source states, green duration masks, yellow, all-red and configured pedestrian phase holds. Randomized tests cover 10 seeds × 3,000 sequential action requests, including negative/out-of-range actions, and verify minimum holds, clearance and protected movement limits in the explicit test model. Tests also reject invalid timing profiles and conflicting protected source states.

Zero violations means **zero violations of these explicit software invariants**, not a proven absence of all roadway conflicts. Imported OSM source phases and permissive `g` movements require SUMO yielding semantics. Agency phase diagrams, field clearance calculations, jurisdictional pedestrian rules and comprehensive conflict surveys are absent. The five-city smoke episodes contain cars, not a pedestrian or transit safety study. Single-phase generated signals left on SUMO's native program are outside the adaptive actuator trace.

Sensor failure invokes deterministic controller fallback; no learned model can bypass actuation masks. Fallback quality can be poor under outages and must be evaluated separately from timing safety. A source outage is not inferred to mean an empty road.

Emergency request verification requires an HMAC signature, issuance/expiry, a supported request kind and an unused nonce. Camera classification cannot sign requests. The verification primitive is tested; downstream emergency/transit phase coordination and measured response-time effects are **not implemented**. No traffic hardware connection or field preemption is present.

Operational ingestion, simulation submission and advisory approval/rejection/rollback require server-side `ATLAS_OPERATOR_KEY`. Keys are never exposed in build-time public variables. Public data exploration and pilot arithmetic remain read-only. The local UI keeps a supplied operator key only in component memory and clears the field upon submission. This is a single-operator foundation, not multi-tenant enterprise identity or hardware certification.
