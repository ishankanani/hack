# Shubha Vivaham — South Indian temple-wedding invitation (mobile)

A standalone, mobile-first digital wedding invitation. Plain HTML/CSS/JS — no build step, no dependencies.
All artwork (temple door, gopuram, garlands, banana leaves, frames) is drawn with CSS/SVG in this folder.

## Open it
Open `index.html` in a browser, or serve the folder:
```bash
cd invitation && python3 -m http.server 8080   # http://localhost:8080
```
It is designed for phone screens; on desktop it shows as a centred phone-width column.

## Flow
1. Temple doors with garlands — **tap to open** (3D door-swing)
2. Rising gopuram over a sunrise valley + falling petals
3. Arched parchment invitation (|| Shri Ganeshaya Namaha ||, couple, parents, venue)
4. Live countdown
5. Scratch-to-reveal *Save the Date* card (with a Reveal fallback button)
6. Bride & Groom temple-arch portrait frames
7. Family members
8. Ritual timeline on banana leaves (Haldi → Reception)
9. Love-story timeline
10. Coverflow gallery (swipe / arrows / dots, tap to enlarge)
11. Venues with address, schedule, *Get Directions* and embedded map
12. RSVP (attend / decline, guest count, blessings → pre-filled WhatsApp message) + Wishes wall
13. Contact cards (call / WhatsApp)
14. Closing card with hashtag copy

## Personalise
Edit **`config.js`**: names, parents, date/time (`weddingAt`), events, story, venues, contacts,
the RSVP WhatsApp number, and starter wishes. To use real photos, set any `photo` field to an image
path (e.g. put files in `invitation/photos/` and use `"photos/groom.jpg"`); empty fields show an
illustrated monogram instead.

Note: new wishes are saved in the visitor's browser only (localStorage) — there is no backend yet.
RSVPs are delivered by opening WhatsApp with the message pre-filled.
