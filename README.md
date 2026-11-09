# The Witcher 3: Next-Gen NSFW Romance & Brothel Scenes Overhaul

[![Game Version](https://img.shields.io/badge/Witcher%203-Next--Gen%204.04%20%2F%205.01-informational?style=flat-square&logo=gogdotcom)](https://www.thewitcher.com/)
[![Status](https://img.shields.io/badge/Status-Work%20in%20Progress%20(Alpha)-orange?style=flat-square)](https://github.com/0xra0/witcher3-nsfw-mod)
[![Contributions Welcome](https://img.shields.io/badge/Contributions-Welcome%20%2F%20Help%20Wanted-brightgreen?style=flat-square)](https://github.com/0xra0/witcher3-nsfw-mod/pulls)
[![Blender](https://img.shields.io/badge/Blender-4.2%2B%20%2F%204.5%2B-F5792A?style=flat-square&logo=blender&logoColor=white)](https://www.blender.org/)
[![REDkit](https://img.shields.io/badge/REDkit-Companion-CD202C?style=flat-square)](https://store.steampowered.com/app/1671760/The_Witcher_3_REDkit/)
[![Age Rating](https://img.shields.io/badge/Content-NSFW%2018%2B-red?style=flat-square)](#)

> [!WARNING]
> **Adult Content Notice (18+):** This modification contains uncensored nudity, sexual content, and anatomical adult themes intended exclusively for mature audiences.
> 
> **Work-in-Progress (WIP):** This mod is in active development and playtesting. It is playable and functional in-game, but some animations, camera transitions, and mesh alignments are still being refined. **If you have experience in 3D animation (Blender), REDkit scene design, or WitcherScript coding, your contributions, testing, and feedback are warmly welcomed!**

---

## 📖 Overview

This project is an open overhaul of the adult romance and brothel encounters in **The Witcher 3: Wild Hunt (Next-Gen / Remastered v4.04 & v5.01)**. 

Vanilla Witcher 3 romance encounters enforce strict camera obscurities, underwear meshes (`_panties` appearances), and censored cutscene branches (such as `sex_do_component_censored` and `release_jp >= 1` condition gates). This mod removes those restrictions and reconstructs the scenes into fully uncensored, immersive, and anatomically accurate experiences.

### Key Highlights
- **Full Uncensoring of Brothel Scenes:** Covers all 6 Novigrad brothel encounters (3 at the Passiflora, 3 at Pegleg Peggy's) and 3 Toussaint encounters (Belles of Beauclair).
- **Scene Routing & Appearance Rewiring:** Patches the CR2W `.w2scene` flow graphs directly so partners immediately switch to `_naked` appearances at scene start rather than lingering in underwear.
- **Dynamic Physics & Bone Rigging:** Integrates custom character rigs (`man_base.w2rig`, `woman_base.w2rig`, `breast_type_1.w2rig`) with dynamic soft-body physics (`.dyng`) for anatomically reactive motion.
- **Custom Animations & Blender Pipeline:** Includes rewritten cutscene actions with multiple variants:
  - **Full Intercourse** (Iterative builds up to `v54`)
  - **Handjob Variant** (`hj1` – `hj15`)
  - **Oral / Blowjob Variant** (`bj1`)
- **Cinematic Exposure & Lighting:** Brothels in vanilla Witcher 3 are lit only for specific distant shots, causing close-ups to appear pitch black. The mod automatically injects an ambient fill light entity (`brothel_fill_light.w2ent`) and boosts cutscene exposure (+2.0) during encounters.
- **Diagnostic & Camera Suite (`modBrothelDiag`):** Complete WitcherScript suite providing real-time in-game appearance locking, free-camera orbit/zoom tools, and live bone-pose distance telemetry.

---

## 🛠️ Current Status & What Works

| Feature | Status | Details |
|---|---|---|
| **Novigrad Brothels (Passiflora 1-3)** | ✅ Implemented | Regular route forced; partner appearance switched to `_naked`. |
| **Novigrad Brothels (Pegleg Peggy 1-3)** | ✅ Implemented | All cutscene sections routed to uncensored branches. |
| **Beauclair Brothels (Belles of Beauclair 1-3)** | ✅ Implemented | Flow conditions rewired to regular side; underwear stripped. |
| **Appearance Lock (`brothel_naked_lock.ws`)** | ✅ Functional | Prevents engine from falling back to panties; strips garters & lingerie tops. |
| **Dynamic Anatomy Physics (`.dyng`)** | ✅ Working | Physics simulation applied to male anatomy bones; natural motion. |
| **Barefoot Lower Body Mesh** | ✅ Working | Custom `ls_02_wa__body_barefoot.w2mesh` removes prostitute stockings. |
| **Exposure / Lighting Fix** | ✅ Functional | Auto-triggers +2.0 exposure and injects `brothel_fill_light.w2ent`. |
| **Animation Precision (Hands / Mouth / Pelvis)** | 🚧 WIP | Hand alignments (`hands_her.py`) and oral alignments (`mouth_her.py`) playable, fine-tuning needed. |
| **Main Story Romances (Yennefer, Triss, etc.)** | ⏳ Planned | Currently focused on brothel encounters; story romances can be adapted using this pipeline. |

---

## 🤝 Community Contributions: Help Wanted!

This repository is shared publicly so that modders, 3D artists, and community members can collaborate, improve, and expand upon the foundation built here.

### Where You Can Help:
1. **3D Animators (Blender / Havok):**
   - Refine bone trajectories in `blender/sex_do_component_import.blend`.
   - Smooth out transitions between lead-in animations and the main cutscene loop.
   - Adjust hand and mouth contact points to avoid clipping across various partner body shapes.
2. **REDkit Scene Designers:**
   - Review and polish the flow graphs in `depot/gameplay/community/dialogues/brothels/*_sex.w2scene`.
   - Create custom dynamic camera tracks and field-of-view angles for enhanced immersion.
3. **WitcherScript Coders:**
   - Extend `modBrothelDiag` with configurable mod-menu options (exposure level, camera auto-orbit speeds, toggleable variants).
   - Add compatibility checks for other popular lighting and weather overhauls.
4. **Playtesters:**
   - Test encounters with various companion mods, report clipping, lighting quirks, or load order conflicts.

---

## 📦 Requirements & Recommended Mods

To get the full uncensored visual presentation, install the following companion mods alongside this mod:

1. **[Naked Geralt With Penis And Muscular Body (GeraltX)](https://www.nexusmods.com/witcher3/mods/11047)**  
   *Essential for Geralt:* Replaces `l_01_mg__body.w2mesh` and underwear models so Geralt renders completely uncovered with full anatomy.
2. **[Women Textures 4K With Vagina Remaster Ready (FemaleTexturesRR)](https://www.nexusmods.com/witcher3/mods/14177)**  
   *Recommended for Partners:* Provides high-resolution 4K skin and intimate textures for female characters.
3. **[The Witcher 3 Script Merger](https://www.nexusmods.com/witcher3/mods/484)**  
   *Standard modding utility:* Needed to merge scripts if you use other WitcherScript mods.

---

## 🚀 Installation

### Option 1: Quick Install (Ready-to-Play Release)
1. Download the latest `Witcher3-NSFW-Mod-v0.54-WIP.zip` from [GitHub Releases](https://github.com/0xra0/witcher3-nsfw-mod/releases).
2. Extract the archive into your The Witcher 3 installation directory:
   ```text
   <The Witcher 3 Wild Hunt>/
   └── mods/
       ├── modBrothelNewScene/    <-- Cutscene bundles, rigs & meshes
       └── modBrothelDiag/        <-- Appearance lock & camera scripts
   ```
3. If you have other script mods installed, run **Script Merger**.
4. Launch the game and visit any brothel in Novigrad (Passiflora or Pegleg Peggy's) or Beauclair.

### Option 2: Building from Source
If you are developing or customizing the mod:
1. Clone the repository:
   ```bash
   git clone https://github.com/0xra0/witcher3-nsfw-mod.git
   cd witcher3-nsfw-mod
   ```
2. The pre-cooked release assets are located in `newscene/modBrothelNewScene` and `diag/modBrothelDiag`.
3. To re-cook cutscenes with REDkit's `wcc_lite.exe` under Linux / Wine:
   ```bash
   ./tools/cook_override.sh work/override_v54
   ```

---

## 🎮 In-Game Controls & Diagnostic Console

The companion `modBrothelDiag` includes a comprehensive debug and cinematic suite accessible via the in-game console (`~` key).

| Console Command | Description |
|---|---|
| `bdiag()` | Scans a 12m radius and logs all nearby NPCs, current appearances, and tags. |
| `bnaked()` | Instantly forces nearby brothel NPCs into their `_naked` appearance. |
| `bpanties()` | Resets nearby brothel NPCs back to their `_panties` appearance. |
| `fcam()` | Toggles the engine's free camera on and off. |
| `bautocam()` | Toggles whether the free camera automatically engages when a brothel encounter starts. |
| `borbit(degrees)` | Orbits the free camera around the active partner by the given angle. |
| `bzoom(meters)` | Smoothly moves the free camera closer to or further from the partner. |
| `bup(meters)` | Adjusts the free camera height. |
| `bfocus()` | Re-centers and focuses the free camera directly on the scene partner. |
| `bpose()` | Toggles the live HUD telemetry probe (reports relative pelvis distance `d`, root offset `r`, heading delta `h`, and elevation `gz`/`hz` every 2 seconds). |
| `bshot()` | Takes a clean HUD-free screenshot. |
| `bcampos()` | Prints current free camera coordinates to the console. |

> [!TIP]
> The **Naked Lock Timer** runs automatically in the background. As soon as a brothel dialogue or cutscene starts, it locks the partner nude, hides residual garters/tops, boosts room exposure to +2.0, and restores everything automatically when the scene concludes.

---

## 📁 Repository Structure

```text
witcher3-nsfw-mod/
├── README.md                      # Project documentation and guide
├── body.blend                     # Master body mesh setup in Blender
├── blender/                       # Blender animation, retargeting & camera tools
│   ├── sex_do_component_import.blend  # Cutscene scene file with rigs & timeline
│   ├── retarget_slal.py           # SLAL / Havok animation retargeter
│   ├── add_penis_bones.py         # Dynamic bone generator
│   ├── camera_pov.py              # First-person POV camera generator
│   ├── hands_her.py               # Hand placement & alignment solver
│   └── mouth_her.py               # Facial & mouth positioning solver
├── depot/                         # Patched CR2W v164 scene graph sources
│   └── gameplay/community/dialogues/brothels/
│       ├── brothels_novigrad_rich_district_passiflora_girl_*.w2scene
│       └── brothels_novigrad_brothel_district_peggleg_peggys_girl_*.w2scene
├── diag/modBrothelDiag/           # WitcherScript runtime mod
│   └── content/scripts/local/
│       ├── brothel_naked_lock.ws  # Real-time nude lock, exposure & clothing hiding
│       ├── brothel_diag.ws        # Console commands & camera controls
│       └── brothel_pose.ws        # Telemetry pose probe
├── newscene/modBrothelNewScene/   # Ready-to-install cooked mod package
│   └── content/
│       ├── blob0.bundle           # Cooked cutscene, rig, entity & mesh assets
│       ├── buffers0.bundle        # 65 binary geometry & animation buffers
│       └── metadata.store         # Package metadata store
├── redkit_mcp/                    # Local MCP server for safe REDkit depot inspection
│   └── server.py                  # Python 3 stdio MCP server for REDkit r4data
├── tools/                         # Automated build, patching & geometry tools
│   ├── cook_override.sh           # Wine + wcc_lite automated cooking pipeline
│   ├── cr2wbuild.py               # Low-level CR2W binary builder
│   ├── dyngio.py                  # Dynamic physics (.dyng) reader and writer
│   ├── penis_dyng.py              # Soft-body dangling physics generator
│   ├── sculpt_vulva.py            # Geometric vulva mesh sculpting tool
│   ├── crotch_weights.py          # Vertex weight re-skinning utility
│   ├── patch_cooked_v07.py        # Retail scene patcher & rewire utility
│   └── rewire_appearance_calls.py # Graph link rewiring for AppearanceChange
└── vendor/                        # Vendored dependencies & Blender addons
    ├── io_scene_nifly/            # Blender Havok HKX / NIF import-export addon
    └── blender-mcp/               # Blender MCP integration
```

---

## 🔬 Technical Deep-Dive

### Why Vanilla Edits Failed and How This Fixes It
In unmodded Witcher 3, editing `CStorySceneCutsceneSection.actorOverrides[].appearance` has **no visible effect** on brothel NPCs because the game reuses the live world actor. Instead, the partner's appearance is controlled exclusively through `CStorySceneScript` nodes that execute:
```c
AppearanceChange_scene(opponentTag, appearanceName) -> CActor.SetAppearance
```
In the vanilla retail flow, the execution order was:
```text
[pre_0X (saves look as _panties)] ──> [AppearanceChange(_naked)] ──> [sex_do_component] ──> [AppearanceChange(_panties)] ──> [after_0X]
```
Because the opening sections and fallback loops were re-applying `_panties`, any disruption or branch transition left the partner wearing lingerie.

**Our Solution:**
1. Direct CR2W graph pointer rewiring (`tools/rewire_appearance_calls.py`) shifts the `AppearanceChange(_naked)` call to the absolute scene entry point, routes all paths into `sex_do_component`, and postpones `AppearanceChange(_panties)` until final exit.
2. The runtime daemon `brothel_naked_lock.ws` acts as a fail-safe: it monitors active cutscenes, forcibly maintains `_naked` appearance state, and hides leftover clothing components (such as garters on Passiflora 08 / Beauclair 02).

---

## 📄 License & Attribution

- **Game Assets & Engine:** The Witcher 3: Wild Hunt, REDengine 3, and REDkit are trademarks and property of **CD PROJEKT S.A.**
- **Mod Source & Tools:** Scripts and tools in this repository are provided freely for personal, non-commercial modding use under an open community license.
- **Third-Party Assets:**
  - `io_scene_nifly`: Created by the Nifly development team for Havok/Blender interop.
  - Companion mods (GeraltX and FemaleTexturesRR) are the property of their respective creators on Nexus Mods and are not redistributed in this repository.

---

<p align="center">
  <b>Developed by the Witcher 3 Modding Community</b><br>
  Pull requests, issue reports, and animation improvements are always welcome!
</p>
