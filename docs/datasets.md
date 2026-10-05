# Sources, licenses, and evaluation splits

| Source | Use | License / scope | Acquisition |
|---|---|---|---|
| [Mixkit #1755](https://mixkit.co/free-stock-video/city-busy-traffic-intersection-time-lapse-1755/) | actual demo footage and CPU inference | Stock Video Free License; source is time-lapse and must not be redistributed as a standalone stock asset | `atlas demo --download-only`; no raw footage committed |
| [dronefreak/visdrone-yolov8n](https://huggingface.co/dronefreak/visdrone-yolov8n/tree/b5ca8d362341457ad715a5314da0931ea58bb237) | aerial detector weights | upstream AGPL-3.0 model card; trained by the model author on VisDrone | downloaded lazily at pinned revision; SHA-256 verified |
| [Ultralytics YOLO11](https://docs.ultralytics.com/models/yolo11/) | configurable COCO detector | upstream AGPL-3.0; pretrained model, no ATLAS fine-tuning claim | downloaded by Ultralytics |
| [COCO8](https://docs.ultralytics.com/datasets/detect/coco8/) | detector evaluation smoke check | eight-image subset of COCO; four validation images; not traffic-domain accuracy; pretrained COCO overlap is possible | `atlas evaluate --only cv` |
| User-supplied MOT CSV | official tracking evaluation | operator supplies licensed footage and matching ground truth; class/ignore-region preprocessing must be documented | `atlas evaluate --only tracking --gt ... --pred ...` |
| Generated conflict scenarios | reproducible risk-model development | ATLAS generator; 6,000 train / 2,000 validation / 3,000 test scenarios | seeds 1001 / 2002 / 3003 |
| Generated diurnal traffic | causal feature and forecast comparison | ATLAS generator; no public-road prediction claim | seed 4444, temporal split at minute 1728 / 2304, horizon-purged training targets |
| Seeded simulator arrivals | paired signal control | explicitly simulated Poisson arrivals, no field trial | tuning seeds differ from evaluation seeds 42 / 43 / 44 |

## Demo provenance

The 1280×720, 480-frame, roughly 20-second aerial sample is time-lapse. `data/demo-attribution.json` records its source, license, and SHA-256. The committed `artifacts/demo/result.json.gz` contains output from a **real detector/tracker run**, with a manifest and source checksum. Restoring it changes the run's local video identifier and marks the provenance cached; it does not synthesize new detections or benchmarks. The source hash must match before restore.

Generic COCO models performed poorly on this overhead frame during model selection. ATLAS therefore uses aerial weights for the supplied sample and retains a COCO profile for street-level footage. This is a qualitative domain-selection finding, not a reported detection accuracy experiment. The sample was used for engineering and model selection and must not later be treated as an untouched test set.

Sample road regions are manually drawn image polygons. No surveyed road dimensions or real capture-time scale are available, so calibration is unverified and physical safety/speed analysis is disabled. Time-lapse, occlusion, tiny road users, and identity fragmentation bias counts and arrival-rate estimates. There is no facial-recognition or person-identity dataset.

## Public traffic datasets / optional fine-tuning

The API supports loading trusted custom detector weights through `ATLAS_MODEL`; use the COCO profile only when the weight class names map to the supported traffic classes. Ultralytics' [VisDrone preparation documentation](https://docs.ultralytics.com/datasets/detect/visdrone/) provides acquisition/preprocessing instructions. [VisDrone's official project](https://github.com/VisDrone/VisDrone-Dataset) governs dataset terms; do not assume that a model card's license grants rights to redistribute the dataset.

For optional fine-tuning, prepare licensed data with explicit train/validation/test files, use `yolo detect train model=yolo11n.pt data=path/to/data.yaml seed=42`, then validate held-out test data with `yolo detect val model=path/to/best.pt data=path/to/data.yaml split=test`. The standard repository tests do not download large traffic datasets or train models. Report dataset version, classes, ignored regions, camera/site split, temporal grouping, and preprocessing with any resulting artifact. Keep overlapping video frames and the same camera/site out of both training and test sets.


## Real evaluation datasets

UA-DETRAC, METR-LA, and RESCO Cologne1 are downloaded separately with pinned revisions and verified content. See [sources, usage terms, preprocessing, and acquisition](real-world-evaluation.md#sources-versions-and-rights). Raw datasets are ignored and not redistributed. Original code licenses do not automatically license the data.
