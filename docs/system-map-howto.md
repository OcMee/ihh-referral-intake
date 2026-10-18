# How to make an interactive system map

The pattern behind [system-map.html](system-map.html). We first saw it on team Lamplight's demo
site at the event and rebuilt it from scratch for our own pipeline. Reuse it for the next
challenge.

## What it is

An interactive system map, also called an architecture walkthrough. A data-flow diagram where:

- boxes are grouped into zones (who sends, what runs locally, what goes outside, what is public);
- each box names the file that does the work;
- a step player (Back · Play · Next) lights up one stage at a time, moves a dot along the arrows,
  and explains the stage in plain words below.

Why it works for judges: in 60 seconds it shows where the data goes, where AI is used, where
plain code checks the AI, and where a person decides.

## How it is built

One HTML file, no libraries. An SVG is drawn from four lists at the top of the script:

| List | Holds |
|---|---|
| `zones` | dashed background areas: `[x, y, w, h, label]` |
| `nodes` | boxes: `id: [x, y, w, h, title, lines, kind, file]`, kind = ai, code, person or web |
| `edges` | arrows: `id: [points, dashed, label, labelAt]`, right-angle polylines |
| `steps` | the walkthrough: which nodes light up, which edge chains a dot travels, the text, the files |

The dot uses `path.getPointAtLength()` in a `requestAnimationFrame` loop. Clicking a box jumps to
its first step. Arrow keys work. Reduced-motion users get no moving dot.

## Steps for a new project

1. List the stages of one item's journey, start to finish (8 to 12 steps).
2. Sort them into zones. Always show the "only outside call" separately.
3. Mark each box as AI, code or person. A judge should see code checking the AI.
4. Lay boxes on a grid in a 1200 x 700 viewBox; route arrows at right angles.
5. Write each step's text in plain words, with the real file names.
6. Screenshot light and dark before showing anyone.
