## Idealization Tests

Replacing a realistic focusing element with its ideal thin-lens +
aperture equivalent is a key technique for validating propagation
parameters.

### Strategy

1. **Test all elements at once first.** If realistic and idealized
   beamlines agree, the propagation parameters are likely correct
   for the entire beamline.

2. **If they disagree, test one element at a time.** Replace each
   focusing element individually to isolate which one is causing
   the discrepancy.

3. **Interpreting results:**
   - Small difference (<5% FWHM): Propagation is handling the
     realistic element correctly.
   - Large difference: Either the propagation params need adjustment
     for that element, or the realistic element has physical effects
     (slope errors, figure errors, higher-order aberrations) that
     the ideal model doesn't capture. The agent should reason about
     which case applies.

### When to use
- After initial parameter tuning, before declaring success
- When a discrepancy persists and you can't determine if it's
  numerical or physical
- When validating parameters for a new element type you haven't
  tuned before
