import type { Metadata } from "next";
import Image from "next/image";
import Link from "next/link";
import { Shell } from "@/components/shell";
import evidence from "../../public/ground-truth/summary.json";
import styles from "./ground-truth.module.css";

export const metadata: Metadata = {
  title: "Ground-truth diagnosis | ATLAS",
  description:
    "Inspect real-video evidence explaining where the Lankershim SUMO reconstruction diverges from observed traffic.",
};

const report =
  "https://github.com/youssef061204/ATLAS/blob/main/docs/reality-v8-diagnostics.md";
const stages = [
  ["no_birth_association", "No CV birth association"],
  ["before_cv_birth", "Before CV admission"],
  ["before_first_native_sample", "Before native sample"],
  ["after_last_native_sample", "After native exit"],
  ["native_beyond_4m", "Native present, beyond 4 m"],
  ["native_within_4m", "Native within 4 m"],
] as const;

function percent(value: number) {
  return `${(value * 100).toFixed(1)}%`;
}

export default function GroundTruthPage() {
  const north = evidence.oracle_before_after_main.northbound;
  const south = evidence.oracle_before_after_main.southbound;
  const all = evidence.oracle_before_after_main.all;
  return (
    <Shell
      title="Ground truth: where the twin breaks"
      eyebrow="LANKERSHIM / ATLAS 8 RESEARCH DIAGNOSIS"
      action={
        <Link className="button secondary" href="/reality">
          Open synchronized video
        </Link>
      }
    >
      <div className={styles.page}>
        <div className={styles.lead}>
          <span className={styles.kicker}>
            REAL VIDEO · OBSERVED TRAJECTORIES · NATIVE SUMO
          </span>
          <h2>Measure the failure before changing the model.</h2>
          <p>
            ATLAS pairs actual FHWA traffic video with independently annotated
            vehicle motion and a free-running simulation. The current physical
            twin has <strong>not passed validation</strong>. These controlled
            experiments identify where it diverges without presenting simulated
            control as a real-world result.
          </p>
          <div className={styles.actions}>
            <Link className="button" href="/reality">
              Watch video + 3D twin
            </Link>
            <a href={report} target="_blank" rel="noopener noreferrer">
              Read methods and raw artifacts ↗
            </a>
          </div>
        </div>

        <section className={styles.section} aria-labelledby="ablation-title">
          <div className={styles.heading}>
            <div>
              <span className={styles.kicker}>
                CONTROLLED DEVELOPMENT EXPERIMENT
              </span>
              <h2 id="ablation-title">
                The Main Street crossing is the weak link.
              </h2>
            </div>
            <span className={styles.status}>
              Oracle diagnostic · not deployable
            </span>
          </div>
          <p>
            Northbound vehicles start from their first annotated state just
            before Main Street, then SUMO runs freely. A second run starts those
            same vehicles from a later annotated state just after Main Street.
            Southbound admissions, network, signal program and driver settings
            stay fixed. Both runs are scored on the same{" "}
            <strong>
              {all.original_oracle_birth.reference_states.toLocaleString()}{" "}
              observed states
            </strong>
            .
          </p>
          <div className={styles.metricGrid}>
            <div className={styles.metric}>
              <span>Northbound position error</span>
              <strong>
                {north.original_oracle_birth.uncapped_position_mae_m.toFixed(2)}
                <small> → </small>
                {north.downstream_oracle_birth.uncapped_position_mae_m.toFixed(
                  2,
                )}{" "}
                m
              </strong>
              <small>
                Present vehicles ·{" "}
                {north.original_oracle_birth.reference_states} reference states
              </small>
            </div>
            <div className={styles.metric}>
              <span>Northbound states within 4 m</span>
              <strong>
                {percent(
                  north.original_oracle_birth.within_4m_reference_coverage,
                )}
                <small> → </small>
                {percent(
                  north.downstream_oracle_birth.within_4m_reference_coverage,
                )}
              </strong>
              <small>
                All observed northbound states stay in the denominator
              </small>
            </div>
            <div className={styles.metric}>
              <span>Unchanged southbound control</span>
              <strong>
                {south.original_oracle_birth.uncapped_position_mae_m.toFixed(2)}{" "}
                m
              </strong>
              <small>Identical error in both native runs</small>
            </div>
          </div>
          <div
            className={styles.comparison}
            role="img"
            aria-label={`Northbound mean position error falls from ${north.original_oracle_birth.uncapped_position_mae_m.toFixed(2)} to ${north.downstream_oracle_birth.uncapped_position_mae_m.toFixed(2)} metres in a reference-assisted post-junction diagnostic.`}
          >
            <div>
              <span>Before junction</span>
              <i style={{ width: "100%" }} />
              <b>
                {north.original_oracle_birth.uncapped_position_mae_m.toFixed(2)}{" "}
                m
              </b>
            </div>
            <div>
              <span>After junction</span>
              <i
                style={{
                  width: `${(north.downstream_oracle_birth.uncapped_position_mae_m / north.original_oracle_birth.uncapped_position_mae_m) * 100}%`,
                }}
              />
              <b>
                {north.downstream_oracle_birth.uncapped_position_mae_m.toFixed(
                  2,
                )}{" "}
                m
              </b>
            </div>
          </div>
          <p className={styles.caveat}>
            The later start bypasses the uncertain intersection and uses an
            annotated future state. It localizes error in the approach/junction;
            it does not repair the operational predictor. Even this oracle
            bypass places only{" "}
            {percent(
              north.downstream_oracle_birth.within_4m_reference_coverage,
            )}{" "}
            of northbound states within 4 m.
          </p>
          <p>
            A separate length-only test extended the southern incoming SUMO edge
            from {evidence.approach_length_only.before_m.toFixed(2)} to{" "}
            {evidence.approach_length_only.after_m.toFixed(2)} m while retaining
            the initial positions within{" "}
            {evidence.approach_length_only.maximum_initial_pose_shift_m.toFixed(
              2,
            )}{" "}
            m. Position error worsened from{" "}
            {evidence.approach_length_only.position_mae_before_m.toFixed(2)} to{" "}
            {evidence.approach_length_only.position_mae_after_m.toFixed(2)} m.
            More approach space alone is not the repair.
          </p>
        </section>

        <section className={styles.section} aria-labelledby="geometry-title">
          <div className={styles.heading}>
            <div>
              <span className={styles.kicker}>
                SOURCE VIDEO / SURVEY / SIMULATION
              </span>
              <h2 id="geometry-title">
                See the real geometry behind the numbers.
              </h2>
            </div>
          </div>
          <figure className={styles.figure}>
            <Image
              src="/ground-truth/geometry-video-overlay.png"
              width={2080}
              height={800}
              sizes="(max-width: 900px) 100vw, 1200px"
              alt="Actual Lankershim traffic video frame beside a source-video overlay of FHWA surveyed trajectories, official GIS signal marker, and SUMO lane centerlines"
            />
            <figcaption>
              Actual FHWA camera-4 frame and survey-derived overlay. The GIS
              marker is a signal location, not a surveyed stop line. Source
              footage CC BY-SA 4.0; derived trajectory/survey material CC BY-SA
              3.0. Full provenance is in the technical report.
            </figcaption>
          </figure>
          <div className={styles.findings}>
            <div>
              <strong>{evidence.main_street_oracle_turns} / 63</strong>
              <span>
                Completed turns in an initial route trial were actually near the
                modeled Main Street signal. The remaining{" "}
                {evidence.other_intersection_turns_rejected} belong elsewhere or
                lack that local support.
              </span>
            </div>
            <div>
              <strong>
                {evidence.rsm_cycle_pairs_matching_current_report_length} / 875
              </strong>
              <span>
                Consecutive controller timestamps match the current row&apos;s
                completed cycle. Split totals still do not reveal actual lamp
                transitions.
              </span>
            </div>
            <div>
              <strong>
                {evidence.camera3_continuous_frames.toLocaleString()} frames
              </strong>
              <span>
                A second genuine continuous FHWA camera was fully decoded. Its
                sampled views did not verify the Main Street lamp colors.
              </span>
            </div>
          </div>
        </section>

        <section className={styles.section} aria-labelledby="lifecycle-title">
          <div className={styles.heading}>
            <div>
              <span className={styles.kicker}>
                UNCHANGED KNOWN REGRESSION COHORT
              </span>
              <h2 id="lifecycle-title">
                Account for every observed vehicle state.
              </h2>
            </div>
            <span className={styles.status}>Validation pending</span>
          </div>
          <p>
            The earlier 600–1,000 s result contains{" "}
            {evidence.known_reference_states.toLocaleString()} independently
            annotated vehicle states. Missing CV admissions, absent native
            vehicles and spatial errors remain visible in the same denominator.
          </p>
          <div className={styles.lifecycle}>
            {stages.map(([key, label]) => (
              <div key={key}>
                <span>{label}</span>
                <meter
                  min={0}
                  max={evidence.known_reference_states}
                  value={evidence.known_stage_counts[key]}
                >
                  {evidence.known_stage_counts[key]}
                </meter>
                <strong>
                  {evidence.known_stage_counts[key].toLocaleString()}
                </strong>
              </div>
            ))}
          </div>
          <p className={styles.caveat}>
            This interval was already inspected in ATLAS 7. The current study is
            a diagnosis, not a fresh holdout. Real-world signal-control benefit
            remains unmeasured; separate controller comparisons are simulation
            experiments.
          </p>
          <div className={styles.actions}>
            <Link className="button secondary" href="/reality">
              Inspect original footage and tracks
            </Link>
            <Link href="/benchmarks">Browse frozen benchmarks →</Link>
          </div>
        </section>
      </div>
    </Shell>
  );
}
