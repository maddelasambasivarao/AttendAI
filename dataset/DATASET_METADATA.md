# AttendAI Synthetic Attendance Snapshot Dataset

**Data Type**: Synthetic Benchmark Simulation (Strictly Separated from Real Student Records)
**Generation Date**: Auto-generated for Machine Learning Training
**Total Records**: 6,400 snapshots
**Unique Students**: 400
**Subjects**: 4 (CS601, CS602, CS603, MA601)
**Checkpoints**: Classes [10, 20, 30, 40]
**Configurable Threshold**: 75.0%
**Shortage Class Balance**: 32.00% positive (below threshold)

## Zero Data Leakage Policy
Each snapshot at checkpoint $T$ computes features strictly using information from $t \le T$.
Future attendance ($t > T$) is used solely to construct the ground-truth target variable `is_shortage`.
