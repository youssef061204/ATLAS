import { Shell } from "@/components/shell";
import { ArrowDown, ArrowUpRight } from "lucide-react";
import { API } from "@/lib/api";
export default function Page() {
  return (
    <Shell
      title="Built from the road up"
      eyebrow="SYSTEM / ARCHITECTURE"
      action={
        <a
          className="button secondary"
          href={`${API}/docs`}
          target="_blank"
          rel="noreferrer"
        >
          OpenAPI documentation <ArrowUpRight size={14} />
        </a>
      }
    >
      <div className="about-lead">
        <div className="eyebrow">ONE COHERENT SYSTEM</div>
        <h2>
          A video is the input.
          <br />
          An inspectable traffic model is the output.
        </h2>
        <p>
          Python owns inference, analysis, and experiments. Next.js owns
          synchronized visualization. A bounded process pool keeps CV work
          isolated from API requests. SQLite WAL persists run-scoped
          observations without an external database requirement.
        </p>
      </div>
      <div className="architecture-flow">
        {[
          ["INGEST", "Upload / attributed sample / trusted stream"],
          ["PERCEPTION", "YOLO11 → ByteTrack or BoT-SORT"],
          [
            "RECONSTRUCTION",
            "Camera calibration → timestamp regression → trajectories",
          ],
          [
            "INTELLIGENCE",
            "Traffic analytics / conflict screens / causal forecasts",
          ],
          [
            "EXPERIMENT",
            "Seeded car following → adaptive baseline → constrained search",
          ],
          [
            "EXPERIENCE",
            "REST + progress SSE → video overlay + interactive 3D twin",
          ],
        ].map(([n, d], i) => (
          <div key={n}>
            <span>{String(i + 1).padStart(2, "0")}</span>
            <div>
              <strong>{n}</strong>
              <p>{d}</p>
            </div>
            <ArrowDown size={16} />
          </div>
        ))}
      </div>
      <div className="two-column">
        <section className="panel methodology">
          <div className="eyebrow">HONEST BOUNDARIES</div>
          <h3>Observation and experiment are distinct.</h3>
          <p>
            Short videos do not justify 15-minute forecasts. Unverified
            perspective does not justify speeds in meters per second. Synthetic
            risk-model scores do not establish real-world safety accuracy.
            Simulated delay reductions are not field-trial benefits.
          </p>
        </section>
        <section className="panel methodology">
          <div className="eyebrow">PRIVACY & RETENTION</div>
          <h3>Anonymous road users.</h3>
          <p>
            No facial recognition or identity inference. Video remains in local
            file storage until the operator removes the deployment data. Track
            IDs identify objects within one video, not people across recordings.
            The default API is intended for a trusted local research workspace.
          </p>
        </section>
      </div>
      <section className="panel methodology">
        <div className="eyebrow">WHY THESE CHOICES</div>
        <h3>Depth where it changes the product.</h3>
        <p>
          A single Python backend keeps numerical methods close to the
          perception outputs and eliminates serialization hops. A process pool
          bounds inference concurrency. SQLite and files make the demo portable.
          A tested microscopic simulator provides deterministic paired
          experiments without an untested SUMO dependency. No event bus, LLM, or
          container orchestrator is required to understand the system.
        </p>
      </section>
    </Shell>
  );
}
