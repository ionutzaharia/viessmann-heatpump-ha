# ViCare Extras

Home Assistant custom integration that adds what the official
[`vicare`](https://www.home-assistant.io/integrations/vicare/) integration is
missing for Viessmann heat pumps (built for a Vitocal 200-S):

- **`switch.vicare_extras_dhw_circulation_pump`** — turn the DHW circulation
  pump on/off. The Viessmann API has no direct on/off command for this pump,
  so ON uploads an "always on" weekly schedule and OFF uploads an empty one.
- **`vicare_extras.set_circulation_schedule`** — write the pump's weekly time
  program (per-day time windows and cycle modes).
- **`vicare_extras.set_dhw_schedule`** — write the DHW time program
  (`heating.dhw.schedule`) — the daily periods when hot water is produced.
- **`vicare_extras.get_schedules`** — read back both schedules and the valid
  circulation modes (returns response data).
- **Backup buttons + sensor** — *Back up circulation schedule* saves the
  current weekly program into HA storage (survives restarts); *Restore
  circulation schedule* uploads it back to the device (unavailable until a
  backup exists). The *Circulation schedule last backup* sensor shows when the
  backup was taken, with the saved schedule and a readable per-day preview as
  attributes.
- **Copy button** — *Copy DHW schedule to circulation pump* mirrors the DWH
  time program onto the circulation pump schedule (so water circulates exactly
  when hot water is being produced). Tip: press backup first — copying
  overwrites the pump's current schedule.
- **Schedule override (boost)** — `vicare_extras.override_schedules` with
  `minutes: N` saves both current plans, switches DHW **and** circulation to
  always-on, and restores the saved plans automatically when time is up. Also
  available from the UI: set the *Override duration* number and press *Start
  schedule override*; *Cancel schedule override* restores early. The *Schedule
  override ends* sensor shows the restore time (with previews of the saved
  plans as attributes). Calling override again while active extends the timer.
  The pending restore is stored in HA storage, so it survives restarts; if a
  restore attempt fails (e.g. rate limit), it retries every 5 minutes.

  ```yaml
  service: vicare_extras.override_schedules
  data:
    minutes: 90
  ```

Runs alongside the official integration; it authenticates separately with the
same API client ID.

## Before installing: test your device

The exact schedule constraints (valid modes, max entries per day, whether
`end: "24:00"` is accepted) vary by device. Verify against the live API first:

```bash
pip install PyViCare==2.60.2
export VICARE_EMAIL="you@example.com"
export VICARE_PASSWORD="..."
export VICARE_CLIENT_ID="..."   # https://app.developer.viessmann-climatesolutions.com/

python3 scripts/test_api.py           # read-only: prints schedules + constraints, saves a backup
python3 scripts/test_api.py --write   # round-trip write test; restores your schedule afterwards
```

The read-only pass writes `scripts/schedule_backup.json` — keep it, it's your
restore point.

## Install

**HACS:** add this repository as a custom repository (type: Integration),
install "ViCare Extras", restart HA.

**Manual:** copy `custom_components/vicare_extras/` into your HA `config/custom_components/`
directory and restart.

Then: *Settings → Devices & Services → Add Integration → ViCare Extras* and
enter your ViCare email, password, and API client ID (the one you created at
the [Viessmann developer portal](https://app.developer.viessmann-climatesolutions.com/)
for the official integration works fine).

## Services

Days you omit are set to **empty** (feature off that day). Entries per day are
sorted by start time and positions are assigned automatically.

Constraints are device-specific and enforced by the API — check the switch
entity's `available_modes` attribute or call `get_schedules`. On a
Vitocal 200-S (E3_Vitocal): only mode `"on"`, max **4 entries per day**,
**10-minute** time resolution, no overlapping windows; `end: "24:00"` is
valid. Other devices may offer cycle modes like `"5/25-cycles"`.

```yaml
service: vicare_extras.set_circulation_schedule
data:
  mon:
    - { start: "06:00", end: "08:00", mode: "on" }
    - { start: "17:00", end: "22:00", mode: "on" }
  tue:
    - { start: "06:00", end: "08:00", mode: "on" }
  sat:
    - { start: "07:00", end: "23:00", mode: "on" }
  sun:
    - { start: "07:00", end: "23:00", mode: "on" }
```

```yaml
service: vicare_extras.set_dhw_schedule
data:
  mon: [{ start: "05:00", end: "22:00", mode: "on" }]
  tue: [{ start: "05:00", end: "22:00", mode: "on" }]
  wed: [{ start: "05:00", end: "22:00", mode: "on" }]
  thu: [{ start: "05:00", end: "22:00", mode: "on" }]
  fri: [{ start: "05:00", end: "22:00", mode: "on" }]
  sat: [{ start: "06:00", end: "23:00", mode: "on" }]
  sun: [{ start: "06:00", end: "23:00", mode: "on" }]
```

```yaml
# Developer Tools → Services, enable "return response":
service: vicare_extras.get_schedules
```

Example automation — circulation only when someone is home:

```yaml
automation:
  - alias: "DHW circulation follows presence"
    trigger:
      - platform: state
        entity_id: zone.home
    action:
      - service: >
          {% if trigger.to_state.state | int > 0 %} switch.turn_on
          {% else %} switch.turn_off {% endif %}
        target:
          entity_id: switch.vicare_extras_dhw_circulation_pump
```

## Rate limits

The Viessmann Basic API plan allows roughly 1450 calls/day, shared across
everything using your account (including the official integration's polling).
This integration polls every 15 minutes by default (~100 calls/day); change it
under the integration's *Configure* → polling interval if you see
`PyViCareRateLimitError` in the logs.

## Notes

- The circulation pump switch state means "schedule is non-empty", not "pump
  motor is spinning right now" — with cycle modes the pump runs intermittently.
  The live pump state is exposed as the `pump_currently_running` attribute.
- Schedule changes are visible in the ViCare app within a few seconds — handy
  for verification.
