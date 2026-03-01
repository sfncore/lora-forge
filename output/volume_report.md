# Per-Role Dataset Volume Report

## Sample Counts by Role
- mayor: 1622 samples
- deacon: 669 samples  
- crew: 568 samples
- witness: 464 samples
- refinery: 395 samples
- polecat: 134 samples
- boot: 91 samples
- unknown: 28 samples

## Analysis
- **Mayor role confirmed as having most data** (1622 samples, ~41% of total training set)
- **Roles below minimum viable training threshold**: 
  - unknown (28 samples) - likely insufficient for meaningful training
  - boot (91 samples) - may be borderline depending on complexity
  - polecat (134 samples) - minimal but potentially usable with careful hyperparameter tuning

## Recommendations
- Proceed with training mayor adapter first (D.2 task)
- Consider data augmentation or transfer learning for roles with limited samples
- Monitor validation performance closely for low-sample roles