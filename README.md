# Garage

Vehicle maintenance for Home Assistant, with the manufacturer-style schedule built in.

- **A built-in schedule.** Every item carries its normal and severe interval, part numbers, fluid spec, torque values and notes, so the printed guide stays in the drawer. The bundled schedule is the 3rd-gen Toyota Tacoma *Maintenance Map* (credit: Soft Taco, Tacoma World). Its 0–300k chart is reproduced by the test suite column by column.
- **More than one vehicle.** Add Garage once per vehicle; the panel gets a tab for each, badged with what it most needs, and `/garage?vehicle=<name>` opens one directly.
- **Two schedules built in:** the 3rd-gen Toyota Tacoma *Maintenance Map*, and the 2022–23 Hyundai Kona 1.6T AWD from Hyundai's owner's manual, with its "miles or months, whichever comes first" limits.
- **No dongle yet?** Leave the odometer sensor empty and type the mileage into the panel; the newest typed reading or logged mileage stands in, dated.
- **The odometer drives it.** Point it at any odometer sensor (an OBD dongle works well). Garage keeps the last known reading while the vehicle sleeps, and a missing reading is never treated as zero.
- **Your log lives in your own folder,** as plain JSON on a share mounted in Home Assistant. Nothing is ever deleted: removed entries are only marked, and a snapshot is taken each day before the first write.
- **Entities for automations:**
  - `sensor.<vehicle>_<item>_due_in`: miles left; negative means overdue, unknown means never logged.
  - `sensor.<vehicle>_services_overdue` and `sensor.<vehicle>_next_service`.
  - `binary_sensor.<vehicle>_service_due`.
  - `sensor.<vehicle>_odometer_last_known` (long-term statistics).
- **Services:** `garage.log_service`, `garage.set_profile`, `garage.set_odometer` and `garage.export_record`.
- **A service record for a sale.** *Service record* on the Log card opens a printable page (print it or save it as a PDF): where every scheduled item stands and every logged service, newest first. A CSV of the same history is saved beside it in `<folder>/exports/`. Entries corrected after the fact are marked; who logged what, and deleted entries, are left out. Costs are only included when asked for (`costs: true`). Add an optional `vehicle` block to `settings.json` (`year`, `make`, `model`, `trim`, `vin`) to title the record.

## Install

1. Mount a share in Home Assistant (Settings → System → Storage → Add network storage, usage *Media*), e.g. `/media/garage`.
2. Add this repository to HACS as a custom integration repository, install **Garage**, and restart.
3. Settings → Devices & services → Add integration → **Garage**. Pick the schedule, the odometer sensor and a folder name.

To show a picture of the vehicle in the panel, put `truck.png` or `vehicle.png` in the vehicle's folder. Use a transparent background: the panel paints the tile behind it in the theme's colour.

## Development

```
python -m pytest tests
```

The tests need no Home Assistant install.
