<!-- Vendored copy of SPEC.md from the Cyclops Link specification, commit a142686. The conformance fixtures it names are vendored in tests/fixtures/cyclops-link-v1/. -->

# Cyclops Link V1: protocol specification

Status: **Implemented.** Spark 1.4.0, Keeper 0.4.0 and Prism 1.2.0 implement this version independently.
Amendment 1 (display only; the wire format is unchanged): §12 marks are mark sheets each presence exports herself.

Cyclops Link lets the three terminal presences notice each other on one machine:

- **Spark** (Claude Code);
- **Keeper** (Codex);
- **Prism** (Antigravity).

What a presence says through it is only:

> I'm here. This is my truthful coarse state. These are my current activity counts. I'm reaching toward that presence.

Cyclops Link is **not** messaging, orchestration, RPC, IPC command transport, shared memory, model routing or agent
control. There is no server, no network, no shared runtime code, no shared process, no peer commands and no content
exchange.

Each presence independently writes one small file about each of her own sessions and independently reads the others'
files. If a peer is absent, disabled, stale or malformed, nothing breaks.

> Identity owns expression. Host owns composition. The person owns action.
> Shared protocol. Separate creatures.

The three implementations conform to this document and to the fixtures in `fixtures/`, independently. They share no
code. `tools/reference.py` exists only to check that the fixtures agree with this text, and no presence may import it.

The keywords MUST, MUST NOT, SHOULD and MAY are used in their usual sense.

---

## 1. Consent: off by default

1. Each presence has her own explicit `link` setting, and its default is **off**.
   - Spark: the plugin option `link`.
   - Keeper: a Codex plugin setting or `--link` flag of her choosing.
   - Prism: `--link` or `PRISM_LINK=1`.
   - There is **no** shared switch: a variable such as `CYCLOPS_LINK=1` MUST NOT enable any presence. Installing a
     presence never implies consent.
2. With Link off, a presence MUST NOT:
   - create the Link directory or the salt;
   - write a Link file;
   - read or `stat` peer files;
   - run a Link heartbeat;
   - poll.
3. Turning Link off while it is active MUST:
   - stop the heartbeat and polling;
   - write the session's record once more with `ended: true`, if it can;
   - stop drawing peers.
4. `CYCLOPS_LINK_DIR` only relocates the directory. It never enables Link.

## 2. The directory

```
LINK_DIR = $CYCLOPS_LINK_DIR                      if set and non-empty
         = $XDG_STATE_HOME/cyclops-link          if XDG_STATE_HOME is set, non-empty and absolute
         = $HOME/.local/state/cyclops-link       otherwise
```

1. **Creating it:** if `LINK_DIR` does not exist, a writer creates it (parents included) with mode `0700`.
2. **Using it:** before any use, the presence checks `LINK_DIR` with `lstat`. It MUST be all of these:
   - a directory, not a symlink;
   - owned by the current UID;
   - without group or other permissions (`mode & 0o077 == 0`).
3. **Unsafe directory:** if any of these fails, Link is **refused** for that session. Nothing is read or written, and
   the presence MUST NOT chmod, chown, delete or replace it. The refusal is shown once, quietly (for example in a
   `state` command), and never blocks the host.

## 3. Local identity: the salt, the room and the instance

### 3.1 Salt

`LINK_DIR/.salt` holds exactly **65 bytes**: 64 lowercase hexadecimal characters (32 random bytes from the operating
system's CSPRNG), then `\n`.

- **Creation:** the first writer creates it with `O_CREAT | O_EXCL | O_NOFOLLOW`, mode `0600`. If that fails with
  `EEXIST`, it reads the file someone else just made.
- **Validity:** the salt is valid only if all of these hold:
  - it is a regular file (checked with `lstat`), not a symlink;
  - it is owned by the current UID;
  - `mode & 0o077 == 0`;
  - it is exactly 65 bytes;
  - its first 64 bytes are lowercase hex, and byte 65 is `\n`.
- **Invalid salt:** Link is refused, as in §2.3. The salt MUST NOT be repaired or regenerated over an existing file.
- **Never published:** the salt never appears in a presence file, a log or a display.

### 3.2 Derivation

```
derive(kind, identity) = lowercase_hex( SHA-256( "cyclops-link/v1/" || kind || 0x00 || salt_bytes || identity_bytes ) )[0:16]
```

- `kind` is the ASCII string `room` or `instance`.
- `salt_bytes` is the **32 raw bytes** decoded from the salt hex. The salt has a fixed length, and `kind` is followed by
  `0x00`, so the concatenation is unambiguous.
- **`room = derive("room", canonical_project_identity)`**
  - `canonical_project_identity` is the UTF-8 bytes of the absolute, symlink-resolved (`realpath`) working folder in
    which the host session started, with no trailing `/` except for `/` itself.
  - Bytes that aren't valid UTF-8 are passed through unchanged (Python `os.fsencode`).
  - V1 does not climb to a repository root: the same folder means the same room.
- **`instance = derive("instance", host || 0x0A || host_session_identity)`**
  - `host` is the host vocabulary word (§4).
  - `host_session_identity` is the host's own opaque session or conversation id, as UTF-8 bytes. Different hosts
    therefore can't collide.
  - If the host gives no session id, the presence uses a random 128-bit id created when its session starts.

The raw project path and the raw session id MUST NOT appear in any Link file.

`room` and `instance` are **local pseudonymous identifiers** for correlating presences on one machine. They are not
secrets, credentials or authentication. Anyone who can read `.salt` and guess a path can recompute a room.

## 4. The record

Each session publishes `LINK_DIR/<presence>-<instance>.json`. `<presence>` and `<instance>` MUST equal the record's
own fields.

```json
{"v":1,"presence":"keeper","host":"codex","instance":"3f1c0a9be2d47c55","room":"a81f29c0d3e4b711","state":"tool","tools":2,"branches":0,"reaching":[],"updated_at":1791320000.25,"ended":false}
```

| Field | Type and bounds |
| --- | --- |
| `v` | exactly the integer `1` (`true` and `1.0` are not `1`) |
| `presence` | `spark` · `keeper` · `prism` |
| `host` | `claude-code` · `codex` · `antigravity` |
| `instance` | exactly 16 characters of `[0-9a-f]` |
| `room` | exactly 16 characters of `[0-9a-f]` |
| `state` | one word of §5 |
| `tools` | integer, `0..256` |
| `branches` | integer, `0..32` |
| `reaching` | array, no duplicates, each a presence word, never the record's own `presence` (so at most 2 entries) |
| `updated_at` | finite number of Unix seconds, `> 0` |
| `ended` | boolean |

Rules:

1. **Required fields:** all eleven fields above are required. A missing or out-of-bounds field invalidates the
   **whole** record, with no partial salvage. In every integer field a boolean is invalid, and so is a float, even one
   with no fractional part.
2. **Matching names:** the file name MUST be exactly `<presence>-<instance>.json` for the record's own `presence` and
   `instance`. Otherwise the record is invalid.
3. **Unknown fields:** fields not listed above are ignored. A record with them is still valid.
4. **Versions:** a record whose `v` is not `1` is ignored entirely.
5. **Encoding:** the file is UTF-8 JSON, a single object, at most 4096 bytes.
6. **Host match:** a presence MUST publish the host that matches her name: Spark is `claude-code`, Keeper is `codex`
   and Prism is `antigravity`. A record pairing a presence with another host is invalid.

## 5. The shared state vocabulary

`idle` · `listening` · `thinking` · `working` · `tool` · `waiting` · `compacting` · `stopped` · `interrupted` · `ended`

| State | Meaning, and the only evidence that may produce it |
| --- | --- |
| `idle` | session open, nothing in progress |
| `listening` | the person is typing into this session (only from a host input event) |
| `thinking` | the model is reasoning, **only** where the host exposes reasoning separately from answering |
| `working` | a turn is in progress (the coarse truthful default during a turn) |
| `tool` | at least one tool call is observed in flight **now** (needs a host event at call start) |
| `waiting` | the host has explicitly asked the person to approve or act |
| `compacting` | the host reports context compaction in progress |
| `stopped` | the last turn ended and nothing new has started |
| `interrupted` | the last turn was interrupted |
| `ended` | the session ended (only in a record that also has `ended: true`) |

Rules:

1. Each presence keeps her own richer states. Her adapter maps them down to this vocabulary, and only to a word the
   host evidence supports.
2. **`waiting`** MUST come only from an explicit host request for the person's action or approval. Elapsed time,
   inactivity, silence, a slow command or a timer never produce it.
3. **`thinking`:** where the host can't tell reasoning from answering, use `working`.
4. **`tool`:** without a host event at call start, a presence can't know a call is in flight. She MUST then publish
   `tools: 0` and never publish `tool`.
5. **Unmappable states:** if an internal state has no truthful mapping, the presence keeps her last truthful published
   state. She never substitutes `idle` as a guess.

## 6. Writing, heartbeat and end

1. A real semantic change MUST be published at once (atomic write, §7).
2. While the session is alive and linked, the writer MUST rewrite its record with a fresh `updated_at` at least every
   **5 s**, even if nothing changed.
3. **Inactivity never ends a session.** Only the host's own truthful end-of-session evidence (or Link being switched
   off, §1.3) may publish `ended: true`, with `state: "ended"`.
4. **Grace period:** after publishing `ended: true`, the writer SHOULD delete **its own** file after **60 s**, if it's
   still running. Readers stop drawing an ended record at once, and any record after 15 s.
5. **Own files only:** a writer MAY delete only its own instance's file. It MUST NOT delete, rewrite or "clean up"
   another session's file, its own presence's included.
6. **Silent failure:** any failure to write is silent and non-blocking. Link stops trying for that session after 3
   failures in a row and never retries in a tight loop.

## 7. Atomic writes

1. Write the complete JSON to a temporary file in **`LINK_DIR` itself**.
   - It is created with `O_CREAT | O_EXCL | O_NOFOLLOW` and mode `0600`.
   - Its name starts with `.` and ends in `.tmp`, for example `.keeper-3f1c0a9be2d47c55.8f2c.tmp`.
2. `fsync` it, then `rename` it over the target.
3. Readers never see a partial record. They ignore every name that starts with `.`.

## 8. Reading peers

1. Read only while Link is on and `LINK_DIR` passes §2.
2. **Pace:** poll at most once per second. `lstat` each candidate, and read its contents only when `(mtime_ns, size,
   inode)` changed since the last read.
3. **Names:** consider only names matching `^(spark|keeper|prism)-[0-9a-f]{16}\.json$`.
4. **Reject the file** without reading it if any of these hold:
   - it is not a regular file (`lstat`, so never follow a symlink);
   - it isn't owned by the current UID;
   - it is writable by group or others (`mode & 0o022 != 0`);
   - it is larger than 4096 bytes.
5. **Validate** the content by §4. An invalid record is ignored completely, and an earlier valid copy of that file is
   forgotten.
6. **Skip yourself:** a reader skips its own `<presence>-<instance>` file for the peer list, but uses its own state
   for its outgoing threads (§10).
7. **Present:** a valid record is **present** at reader time `now` only if all of these hold:
   - `ended` is `false`;
   - `now - 15 < updated_at <= now + 2` (stale records and records stamped in the future are both absent);
   - its room is visible under the reader's room policy (§9).

## 9. Rooms and the "everywhere" policy

1. **Same room by default:** by default, a reader draws only present records whose `room` equals its own room.
2. **Everywhere:** a presence MAY offer an `everywhere` display policy, which draws present records from every room.
   It changes only what that reader shows. It never changes what anyone publishes.
3. **Instances:** files are **instances**. A room can hold several of each presence, such as two Keepers or three
   Sparks. Readers MUST NOT merge valid instances. How they are stacked or fanned out is the host's choice.

## 10. Reaching and handoff threads

1. **Semantic only:** `reaching` is semantic. A presence publishes `reaching: ["keeper"]` only when her own
   privacy/semantic adapter has turned a real host fact into a finite event, `peer.reach("keeper")`, and only while
   that call is in progress.
   - The Link layer receives only that finite event. It never receives command text, arguments, paths, prompts, tool
     payloads or call ids, and it never parses command strings itself.
   - When the call ends, the peer leaves `reaching` and the change is published at once (§6.1).
2. **Class, not instance:** `reaching` names a presence **class**, never an instance. `["keeper"]` claims only "I am
   reaching toward Keeper", not which Keeper received anything.
3. **Threads:** given the set of records a reader can see (present peers plus her own record), a thread `A → B` exists
   when both hold:
   - some present (or own, live) record of class A has B in `reaching`;
   - at least one present record of class B is visible.

   The reader draws outgoing threads where A is herself, and arriving threads where B is herself. She MAY draw threads
   between two peers.
4. **No guessing:** B never infers that A called her. A thread exists only because A's own record says so.
5. **No lingering:** a thread disappears when A stops reaching B, when A goes stale or ends, or when no present B
   remains.

## 11. Canonical room geometry

These are V1 constants:

| Presence | Bearing |
| --- | --- |
| Prism | **90°** |
| Spark | **210°** |
| Keeper | **330°** |

Bearings are measured counter-clockwise from screen-right, with screen-up positive.

- **The triangle is fixed:** every presence places each peer in the direction from her own seat to that peer's seat.
  - Spark sees Prism to the upper right and Keeper to the right.
  - Keeper sees Prism to the upper left and Spark to the left.
  - Prism sees Spark to the lower left and Keeper to the lower right.
- **No centre:** there is no master presence.
- **The host decides the rest:** distance, scale, exact placement, stacking of multiple instances, animation, clipping
  and layout.

## 12. Marks and appearance

Link files carry **state, never appearance**: no SVG, ASCII art, colour, animation or drawing instructions.

Each presence owns her canonical look. A host composes a peer only with the look that peer has exported herself, and
never redraws her.

1. **Mark sheets.** Each presence exports a **mark sheet** from her own terminal renderer with her own tool:
   `{"v": 1, "presence", "cols", "rows", "frames", "states_map", "ascii", "note"}` and, optionally, `"core"`.
   - `frames` maps Link states (§5) to a grid of `rows` x `cols` cells, each `[character, foreground, background]`,
     where a colour is `[r, g, b]` (0-255 integers) or `null` (the terminal's own).
   - `idle` is required. `states_map` names the frame a state without its own frame is drawn with. A state in
     neither is drawn with `idle`.
   - `ascii` gives an ASCII-only grid per frame, for hosts that cannot draw Unicode.
   - `core`, when present, is `[x0, y0, x1, y1]` inside each frame: the part a host too small for the whole sheet may
     draw instead.
2. **Vendored, never shared at runtime.** Hosts carry a copy of each peer's sheet, unchanged, with a note naming its
   source and digest, and read only that copy. A sheet is display data: it is never part of a record, never read
   from the Link directory, and never executed.
3. **No invention.** A host that has no valid sheet for a peer draws only that peer's name. It never invents a look.
4. **Text marks** for one-character places (status lines, labels) are declared by each presence:

| Presence | Text mark | ASCII fallback | Declared by |
| --- | --- | --- | --- |
| Spark | `✶` | `*` | Spark (her own idle glyph) |
| Prism | `⟐` | `<>` | Prism |
| Keeper | `◎` | `O` | Keeper (his own eye glyph) |

V1 sheets: Spark 11 x 6 half-block cells (`hooks/render-raster.js`), Keeper 11 x 5 braille cells
(`scripts/terminal_art.py`), Prism 23 x 5 with a 7 x 3 core (`scripts/terminal.py`).

## 13. Privacy contract

A Link file, a Link display and any Link telemetry MUST NEVER contain:

- prompt or response text;
- a command or its arguments;
- a raw tool name or tool result;
- code;
- a file path;
- a model name;
- a user name;
- a raw session or call id;
- a secret or credential;
- anything a tool read or produced.

What may appear is exactly the fields of §4. The `fixtures/privacy.json` cases are adversarial host facts that MUST
NOT leak.

## 14. Failure behaviour

Link is optional presence awareness. None of these may crash, block, slow or alter the host agent:

- directory creation fails;
- the salt is invalid;
- an atomic write fails;
- a peer file is corrupt;
- permissions are unsafe;
- a peer disappears;
- polling fails.

In each case Link degrades to drawing fewer or no peers. It never types into terminals, never retries aggressively and
never changes another session's files.

## 15. Versioning

- **Unknown fields:** readers ignore fields they don't know.
- **Other versions:** readers ignore records whose `v` is not `1`.
- **Breaking changes:** a breaking change is V2.
- **No extensions:** V1 is not extended with RPC, capability negotiation or messages.

## 16. Out of scope for V1

- messaging, chat, or forwarding of prompts or responses;
- shared memory, peer commands, RPC, sockets, HTTP, any networking;
- discovery requests and capability negotiation;
- model routing, launching agents, automatic handoff, orchestration;
- presence across machines;
- reaching a specific instance.

## 17. Conformance

A presence conforms to V1 when, independently and in her own language, she:

1. Reproduces `fixtures/derivation.json` exactly.
2. Accepts or rejects every case in `fixtures/records.json` with the expected outcome. Filesystem cases are recreated
   in a temporary `LINK_DIR`, and those needing another UID are skipped where the test can't create them.
3. For every scenario in `fixtures/views.json`, produces the expected peer list (presence, instance, state, tools,
   branches, bearing from her seat) and thread list.
4. Meets `fixtures/lifecycle.json`: what is written when, the heartbeat, no end from inactivity, and the off state.
5. Meets `fixtures/privacy.json`: none of the forbidden strings appear in her Link file, her peer display or her Link
   telemetry.

The canonical expected outputs and their exact shapes are described in `fixtures/README.md`.
