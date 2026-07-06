// Seed EVA Activity Board with current session tasks.
//
// Seeding now lives in the storage layer (storage.ts → seedIfEmpty), which runs
// automatically on first boot when the dataset is empty. This script simply
// triggers that path and reports the result — no native SQLite driver required.
import { storage, seedIfEmpty } from "./storage";

seedIfEmpty();
console.log(`Activity board seeded — ${storage.getAllActivities().length} tasks present`);
