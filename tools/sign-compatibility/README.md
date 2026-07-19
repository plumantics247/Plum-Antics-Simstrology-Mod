# Sign Compatibility Templates

This folder keeps the `SignCompatibility` XML generated from one verified preference model.

Reference sources:

- Structural model: `C:\Users\timgo\Downloads\chingyu_CustomPreferences_HolidayTradition_EP05.package`
- Category icon sources: reusable assets in `src/core/DstImage`
- Core sign traits: `src/core/Trait/PlumAntics_Big3ModCore_*`

Current implementation notes:

1. The reference package uses one `ObjectPreferenceItem` plus two `Preference` tunings for each like/dislike choice.
2. The generated package therefore creates `36` preference items and `72` preference traits.
3. Hidden buffs and shared channel commodities are included now so every CAS selection attaches XML-only gameplay tuning even before later runtime chart hooks are added.
4. Regenerate the full visible source tree with `node .\tools\sign-compatibility\generate.js`.
