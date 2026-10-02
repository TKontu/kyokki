/**
 * Type Exports
 * Barrel export for all types
 */

export * from './inventory'
export * from './product'
export * from './category'
export * from './receipt'
// `consumption` still declares its own `UndoStep`/`UndoPreview` (unused outside this file);
// `inventory`'s copy - the one the undo screens use, with `direction` (2026-10-02) - wins here.
export type {
  ConsumptionAction,
  ConsumptionLogEntry,
  ConsumptionLogParams,
  ActionSummary,
  ConsumptionSummary,
  UndoResponse,
} from './consumption'
export * from './api'
export * from './vocabulary'
