# Simstrological Mod Gameplay

Last updated: 2026-07-19

This file is a player-facing outline of what makes the main Simstrological Mod special.
For deeper implementation notes and technical history, see `GAMEPLAY_NOTES.md`.

## Release History

### Since V2.51

- a new **Simstrology Hub** brings the main Simstrology options into one place for human teen-and-older Sims. From the Hub, players can start or repair a chart, review chart and sky information, change save-wide settings, or open Cheats and Repairs.
- the chart card includes house placements and current Sun progression. Every Hub card has a clear **Return to main menu** option.
- **Cheats and Repairs** now includes **Change a Sign**, with separate Sun, Moon, and Rising sign pickers. The older duplicate Sim pie-menu entries for these options, chart readouts, settings, and repair tools have been consolidated into the Hub.
- retrogrades now do more than apply moodlets: when the optional Retrogrades add-on is installed, active retrogrades can add small, action-based effects to ordinary play. See [Retrogrades in Everyday Play](#retrogrades-in-everyday-play) below.

### Since V2.1

Since the original `2.1` build, Core has been expanded in a few major player-facing ways.

Key updates:
- outer planets became a real optional gameplay layer, with support for Uranus, Neptune, Pluto, and Chiron transit data, chart readouts, icons, and house-linked effects when the Outer Planets add-on is installed
- natal chart and current-transit readouts became broader and cleaner, so add-on driven information can show up more consistently instead of feeling bolted on
- house and transit state recovery was hardened, including better restoration of house transit buffs and better household refresh behavior after load or repair
- the shared Simstrological clock was tuned further, with broader Mars-plus sky setup support, refined transit timing behavior, and a fresh-sky reseed path for players who want to restart that layer in a save
- everyday onboarding became clearer through better gameplay tooltips, while the shared Friendly social interactions for transits, chart rulers, retrogrades, and natal chart reading were restored and cleaned up
- Big 3 follow-through got stronger for connected saves, including childhood auto-assignment support and a cleaner Core-side bridge for child-to-teen sign handoff recovery
- runtime performance and load stability were improved through additional efficiency guards, legacy cleanup, and better recovery behavior in the universal clock
- older migration-era leftovers were reduced, including removal of obsolete V2-only refresh or upgrade surfaces that no longer matched live gameplay
- compatibility behavior stayed better documented for players using moodlet-priority or emotion-overhaul mods, since those can still make retrograde or lunar moods feel stronger than intended

## Retrogrades in Everyday Play

Alongside their existing moodlets, retrogrades can now affect ordinary gameplay in small ways that fit each planet. These effects require the optional Retrogrades add-on.

- **Mercury** can occasionally add a little extra wear after an eligible object is used. It never forces an object to break.
- **Venus** can make low-relationship social connections slightly less straightforward, while sincere relationship-repair interactions can receive a small boost.
- **Mars** can make an already-completed strenuous activity or repair more tiring. It never forces injuries, fires, or failed actions.
- **Jupiter** rewards mentoring, tutoring, and rereading skill material, encouraging Sims to reconsider what they already know.
- **Saturn** gives a small completion reward after homework, bills, cleaning, and repairs.

Visible retrograde moodlets will keep their existing teen+ boundary. Children may still experience safe, age-appropriate effects through the activities they do, such as homework, exercise, social mix-ups, or wear on objects they use. They will not receive adult romance, career, spending, or retrograde moodlet effects.

Effects are triggered only after an eligible normal action has completed, rather than through arbitrary forced failures. If no relevant retrograde is active, this layer does nothing.

When one of these effects actually happens, the affected Sim receives a normal in-game notice with their portrait and the retrograde that caused it. Notices have a short per-planet cooldown, so repeated actions do not fill the notification wall.

## What This Mod Is

`PlumAntics Simstrological Mod` is the core gameplay package.
It gives Sims a Simstrological identity, tracks their chart state, and powers the shared systems that the rest of the Simstrology line builds on.

This is the V2 version of the mod.
The biggest change from older builds is that the mod now uses Python to run a universal Simstrological clock.

## What V2 Changes

The V2 runtime means the mod no longer feels like a collection of separate sign features.
It behaves more like one connected system.

Key benefits:
- one shared clock drives chart-aware gameplay
- retrogrades are tracked consistently instead of feeling like disconnected one-off effects
- startup is more reliable, so gameplay can restore correctly when loading into a save
- chart systems can share timing, state, and progression more cleanly
- future add-ons like Skill and Career can plug into the same live simulation layer

In player terms, this means the world feels more alive and less static.
The stars are not just labels on a trait panel. They are part of an active gameplay engine.

## Core Gameplay Loop

The main mod is built around onboarding, identity, and shared chart systems.

Players begin by choosing an onboarding lane:
- `Sun First`
- `Rising First`

`Sun First` is the more step-by-step route.
It lets the player build into the chart through Sun, Moon, and Rising.

`Rising First` is the more snapshot-driven route.
It uses Rising as the anchor and lets the broader chart fill in from the current sky.

After onboarding, the two lanes are designed to converge into shared gameplay wherever possible.

## What Players Experience

Once a Sim is onboarded, the core mod can support:
- visible Sun, Moon, and Rising identity
- chart ruler assignment
- dominant chart element and mode markers
- natal chart readouts
- house systems
- progressed Sun systems
- retrogrades
- return-style events such as Moon Return and Solar Return
- compatibility-style sign discovery and social flavor

The goal is for a Sim's chart to feel like an ongoing part of their life, not just a one-time trait assignment.

## Compatibility Note: Moodlet Priority Mods

Simstrology uses moodlets for systems such as retrogrades and lunar moods.
These moods are tuned to be present without taking over the entire emotional stack.

Mods that change moodlet priority, restack moodlets, or rebalance emotional weight may change how prominent Simstrology moods feel in game.
This includes mods such as Roburky's Meaningful Stories and other mood-enhancing or emotion-overhaul mods that reprioritize moodlets.

If one of those mods is installed, retrograde or lunar moodlets may appear stronger, more visible, or more dominant than intended.
For example, if Jupiter retrograde applies a Dazed moodlet, a mood-priority mod may push that Dazed moodlet to the top of every affected Sim's mood stack and make it difficult to work around until Jupiter leaves retrograde.

This is a compatibility behavior with moodlet-priority systems rather than a sign that Simstrology is adding the wrong moodlets.

## Why The Universal Clock Matters

The universal clock is what lets the mod feel dynamic.

Instead of every feature acting alone, the runtime can:
- remember hidden chart state
- restore active systems on load
- keep retrograde timing coherent
- drive notices, buffs, and chart refresh behavior from one live source

This matters even more as the ecosystem expands.
Skill can unlock deeper interpretation.
Career can later turn that knowledge into professional progression.
The core mod becomes the shared astrological world that those add-ons live inside.

## Progression With The Skill Add-On

On its own, the core mod gives Sims their chart identity and shared world systems.
When `PlumAntics Simstrology Skill` is installed, that identity becomes something the player can actively study and develop.

The current progression shape is:
- core gives the Sim a chart
- skill lets the player learn what that chart means
- higher knowledge unlocks richer interpretation gameplay

Level 4 Simstrology is the main interpretation tier in the merged design.
That is where chart reading starts to open up in a more complete way.

## What Makes This Mod Special

The main Simstrological Mod is not just "traits with astrology names."

Its distinctive qualities are:
- two onboarding fantasies: `Sun First` and `Rising First`
- a shared chart-state model behind the scenes
- a live universal Simstrological clock in V2
- merged systems for retrogrades, houses, returns, and chart markers
- strong support for expansion through Skill now and Career later

The fantasy is that Sims do not simply have signs.
They live inside a moving Simstrological world.

## Best Fit For Players

This package is for players who want:
- a core Simstrology framework for the whole save
- charts that matter beyond initial assignment
- dynamic systems like retrogrades and chart-based notices
- a foundation that grows naturally with the Skill, Childhood, and later Career add-ons

If this is the only package installed, it should still feel like a full core identity system.
If the add-ons are installed, it becomes the foundation everything else builds on.
