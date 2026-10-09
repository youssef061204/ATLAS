# ATLAS 2.0 measured evidence

This increment is experimental. The prototype is not promoted over the production controller. No field or proprietary-controller superiority is claimed.

## five-city-nominal.json

Exploratory uncalibrated OSM network smoke experiments; assumed demand, not field impact

| City | Controller | Mean delay ± sample SD | Mean 95% CI | Seeds |
|---|---|---:|---|---:|
| austin | fixed | 59.341 ± 0.577 s | 59.071–59.611 | 20 |
| austin | max_pressure | 50.402 ± 1.146 s | 49.865–50.938 | 20 |
| austin | original_mpc | 47.483 ± 2.070 s | 46.515–48.452 | 20 |
| austin | risk_mpc | 50.401 ± 1.142 s | 49.866–50.935 | 20 |
| calgary | fixed | 18.621 ± 0.313 s | 18.474–18.768 | 20 |
| calgary | max_pressure | 21.264 ± 1.648 s | 20.493–22.035 | 20 |
| calgary | original_mpc | 19.131 ± 2.978 s | 17.737–20.524 | 20 |
| calgary | risk_mpc | 21.264 ± 1.648 s | 20.493–22.035 | 20 |
| london | fixed | 12.089 ± 0.667 s | 11.777–12.401 | 20 |
| london | max_pressure | 9.311 ± 0.600 s | 9.030–9.592 | 20 |
| london | original_mpc | 8.327 ± 0.472 s | 8.106–8.548 | 20 |
| london | risk_mpc | 9.308 ± 0.601 s | 9.027–9.590 | 20 |
| seattle | fixed | 47.796 ± 1.397 s | 47.142–48.450 | 20 |
| seattle | max_pressure | 41.887 ± 2.110 s | 40.900–42.875 | 20 |
| seattle | original_mpc | 38.700 ± 2.572 s | 37.497–39.904 | 20 |
| seattle | risk_mpc | 41.887 ± 2.110 s | 40.900–42.875 | 20 |
| toronto | fixed | 32.874 ± 1.097 s | 32.360–33.387 | 20 |
| toronto | max_pressure | 29.434 ± 1.752 s | 28.614–30.254 | 20 |
| toronto | original_mpc | 27.680 ± 2.101 s | 26.697–28.663 | 20 |
| toronto | risk_mpc | 29.434 ± 1.752 s | 28.614–30.254 | 20 |

Paired prototype comparisons (positive means lower delay):

| City | Baseline | Mean paired reduction | Bootstrap 95% CI | Wins |
|---|---|---:|---|---:|
| austin | fixed | 15.06% | 14.15–15.98% | 20/20 |
| austin | max_pressure | 0.00% | -0.29–0.32% | 7/20 |
| austin | original_mpc | -6.34% | -8.56–-4.06% | 2/20 |
| calgary | fixed | -14.22% | -18.59–-10.99% | 0/20 |
| calgary | max_pressure | 0.00% | 0.00–0.00% | 0/20 |
| calgary | original_mpc | -13.59% | -21.61–-6.01% | 8/20 |
| london | fixed | 22.81% | 20.14–25.43% | 20/20 |
| london | max_pressure | 0.03% | 0.00–0.07% | 3/20 |
| london | original_mpc | -12.15% | -16.19–-7.89% | 2/20 |
| seattle | fixed | 12.28% | 10.00–14.56% | 20/20 |
| seattle | max_pressure | 0.00% | 0.00–0.00% | 0/20 |
| seattle | original_mpc | -8.71% | -12.66–-4.76% | 3/20 |
| toronto | fixed | 10.39% | 7.90–12.83% | 19/20 |
| toronto | max_pressure | 0.00% | 0.00–0.00% | 0/20 |
| toronto | original_mpc | -6.82% | -10.72–-2.90% | 6/20 |
## transfer.json

New unchanged zero-shot prototype comparison; native platform numerical drift remains a limitation

| City | Controller | Mean delay ± sample SD | Mean 95% CI | Seeds |
|---|---|---:|---|---:|
| cologne1 | fixed | 59.793 ± 1.728 s | 58.984–60.601 | 20 |
| cologne1 | max_pressure | 34.807 ± 1.766 s | 33.981–35.633 | 20 |
| cologne1 | original_mpc | 20.490 ± 0.905 s | 20.067–20.914 | 20 |
| cologne1 | risk_mpc | 21.458 ± 2.595 s | 20.244–22.673 | 20 |
| ingolstadt1 | fixed | 36.545 ± 1.606 s | 35.794–37.297 | 20 |
| ingolstadt1 | max_pressure | 27.392 ± 1.965 s | 26.473–28.312 | 20 |
| ingolstadt1 | original_mpc | 42.823 ± 5.061 s | 40.454–45.191 | 20 |
| ingolstadt1 | risk_mpc | 27.329 ± 1.903 s | 26.438–28.219 | 20 |

Paired prototype comparisons (positive means lower delay):

| City | Baseline | Mean paired reduction | Bootstrap 95% CI | Wins |
|---|---|---:|---|---:|
| cologne1 | fixed | 64.07% | 61.76–65.65% | 20/20 |
| cologne1 | max_pressure | 38.29% | 34.94–40.98% | 20/20 |
| cologne1 | original_mpc | -4.69% | -9.95–-0.71% | 6/20 |
| ingolstadt1 | fixed | 25.02% | 22.11–27.95% | 20/20 |
| ingolstadt1 | max_pressure | -0.04% | -3.17–3.06% | 11/20 |
| ingolstadt1 | original_mpc | 35.29% | 31.33–39.23% | 20/20 |

## Interpretation and limits

Five-city routes are assumed demand on small OSM corridors. The prototype can lose to frozen MPC or fixed timing. The topology fallback is pressure control, not proof of improved cooperative optimization. Ingolstadt improvements must be compared with pressure separately. Search latency can be worse. The protocol was frozen before the final cohorts; all seeds and failures remain in the raw evidence.

Controller/demand/source hashes and all metrics are in `artifacts/cities/study-summary.json`. Full raw traces are losslessly compressed alongside it. This study does not establish real-city calibration, pedestrian/transit/emergency outcomes, multi-regime reliability or commercial readiness.
