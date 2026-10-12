# Trail Tracer Rx programmer

A web page that installs firmware on a Trail Tracer Rx board over USB, and the builds that it offers.

Page: https://trtr6842-git.github.io/trailtracer-programmer/ (Chrome or Edge on a computer; Firefox, Safari
and phones do not have Web Serial).

1. Plug the Rx into the computer.
2. Press "Connect an Rx" and choose the board.
3. The page shows only the installs that fit the board, each with the firmware version, its source
   (repository, branch, commit) and what changes on the board. Builds that do not fit show with the reason.
4. Follow the steps that the page shows (for some installs: unplug and plug in the board once).

The page checks the SHA-256 of each file against its manifest before it writes anything.

## Builds

Every 30 minutes a workflow builds the head of each branch of the public firmware repositories
(rctestflight/Trail_Tracer_Mower, rctestflight/Trail-Tracer) that has no build yet, with PlatformIO. It keeps
the newest 10 builds of each branch. Before it publishes, it checks every file of the site; one finding
stops the publish. The check reads its word lists from the repository secret GATE_LISTS; without it nothing is published.

| Path | What |
|---|---|
| page/ | the page: index.html, program.js |
| tools/build_all.py | builds the branch heads |
| tools/make_manifest.py | writes the manifest of one build |
| tools/check_site.py | the check before a publish |
| site branch | the published site: the page and builds/ |
| builds/index.json | the list of builds |
| builds/<repo>/<branch>/<commit>/manifest.json | one build: chip, version, source, files with SHA-256 |

STM32 builds are signed, encrypted update files that only the board's update loader can use.
