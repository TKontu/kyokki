/**
 * English message catalogue (Post-MVP frontier item 13, phase 2): the source of every key.
 * `fi.ts` is typed against this file (`Messages = typeof en`), so a key missing there - or
 * typed differently, e.g. a plain string where this has a plural pair - fails `tsc`.
 *
 * English is also the runtime fallback (`lib/i18n/index.ts`'s `t()`): any key a language's
 * catalogue does not resolve to a string falls back to this file's value, same as a product's
 * own `display_names` falling back to its canonical name.
 *
 * Out of scope this phase (unchanged, still English only): the products screen, the receipt
 * screens, `/scan`, `/area`, the scanner components, `components-demo` and `fridge-mocks` -
 * none of their text runs through this catalogue yet.
 */

export const en = {
  shell: {
    nav: {
      main: 'Main',
      stock: 'Stock',
      shopping: 'Shopping',
      receipts: 'Receipts',
      products: 'Products',
      gone: 'Gone',
      more: 'More',
      settings: 'Settings',
    },
  },
  status: {
    retry: 'Retry',
    retryLabel: 'Retry {label}',
    failed: '{label} failed',
    dismiss: 'Dismiss',
    dismissLabel: 'Dismiss {label}',
    more: 'and {count} more',
    unreachable: 'Not reaching the kitchen server',
    showingFrom: ' · showing stock from {when}',
    tryAgain: 'Try again',
    lastUpdated: 'Last updated {when}',
  },
  common: {
    close: 'Close',
    tryAgain: 'Try again',
    keepMine: 'Keep mine',
    useTheirs: 'Use {value}',
    fieldChangedWhileOpen: '{label} changed to {value} while this was open',
    cancel: 'Cancel',
    add: 'Add',
    back: 'Back',
    save: 'Save',
    delete: 'Delete',
    location: 'Location',
    expiry: 'Expiry',
    category: 'Category',
  },
  errorScreen: {
    title: 'Something went wrong',
    body:
      'Kyokki hit an error it could not recover from on its own. It is trying again by ' +
      'itself, so you can leave this screen alone.',
    retry: 'Try again',
  },
  badge: {
    expiry: {
      expired: 'Expired',
      today: 'Today',
      days: '{count}d',
      tenPlus: '10d+',
    },
    status: {
      sealed: 'Sealed',
      opened: 'Opened',
      partial: 'Partial',
      empty: 'Empty',
      discarded: 'Discarded',
    },
  },
  fridge: {
    staleStrip: {
      heading: 'Going stale',
      ariaLabel: 'Going stale',
      clearExpired: 'Clear expired',
      more: 'More',
      allAriaLabel: 'All going stale',
    },
    areaSpot: {
      empty: 'Empty',
      open: 'Open {area}',
      moreInside: 'More inside',
    },
  },
  home: {
    add: '+ Add',
  },
  inventory: {
    fridgeView: {
      loading: 'Loading inventory',
      loadError: 'Failed to load inventory.',
      empty:
        'No items found. Add one with + Add, or share a receipt to the Telegram bot - you can ' +
        'also scan one from Receipts.',
    },
    consumption: {
      usedUp: 'Used up',
      editItem: 'Edit item',
      usedUpToast: 'Used up · {name}',
      usedUpError: 'Could not update {name}',
    },
    clearExpired: {
      title: { one: 'Clear {count} expired item?', other: 'Clear {count} expired items?' },
      cancel: 'Cancel',
      confirm: 'Yes, throw away',
      body:
        'This records them as thrown away, which is what the waste count is for. Anything ' +
        'you actually ate is better consumed from its card instead.',
      toast: {
        one: 'Thrown away · {count} item',
        other: 'Thrown away · {count} items',
      },
      error: {
        one: 'Could not clear {count} item',
        other: 'Could not clear {count} items',
      },
    },
    itemEdit: {
      cancel: 'Cancel',
      confirmDelete: 'Yes, delete',
      deleteBody:
        'Delete {name}? This removes the item; what it wasted stays on Gone. Use Mark as ' +
        'gone if it was thrown away.',
      save: 'Save',
      markAsGone: 'Mark as gone',
      putItBack: 'Put it back',
      delete: 'Delete',
      addedOn: 'Added {date}',
      fromLineAndText: 'From {store}, {date}: {line}',
      fromLine: 'From {store}, {date}',
      categoryLine: 'Category: {category}',
      noCategory: 'No category',
      change: 'Change…',
      changeProductDetails: 'Change product details…',
      expiry: 'Expiry',
      location: 'Location',
      loadingProductDetails: 'Loading product details…',
      productDetailsError: 'Could not load the product details for {name}.',
      backTo: 'Back to {name}',
      freezerDateNote:
        'Saving will give this a freezer date. Taking it back out later will not change it ' +
        'back — set the date yourself then.',
      freezerKeptNote: 'Your date will be kept, not the freezer one.',
      savedToast: 'Saved · {name}',
      saveError: 'Could not save {name}',
      deletedToast: 'Deleted · {name}',
      deleteError: 'Could not delete {name}',
      markedGoneToast: 'Marked as gone · {name}',
      backInKitchenToast: 'Back in the kitchen · {name}',
    },
    quickAdd: {
      title: 'Add to stock',
      newProduct: 'New product',
      category: 'Category',
      location: 'Location',
      expiry: 'Expiry',
      back: 'Back',
      add: 'Add',
      addedToast: 'Added · {name}',
      addError: 'Could not add {name}',
    },
    undo: {
      undo: 'Undo',
      undoDescribed: 'Undo {description}',
      error: 'Could not undo',
    },
  },
  shopping: {
    header: {
      title: 'Shopping',
      generate: 'Generate from low stock',
    },
    empty: 'Nothing on the list.',
    groups: {
      urgent: 'Urgent',
      normal: 'Normal',
      low: 'Low',
      other: 'Other',
    },
    bought: 'Bought ({count})',
    clearBought: 'Clear bought',
    boughtToast: 'Bought · {name}',
    undo: 'Undo',
    undoFailedToast: "Couldn't undo; it's still ticked",
    retry: 'Retry',
    updateError: 'Could not update {name}',
    removeError: 'Could not remove {name}',
    addError: 'Could not add {name}',
    clearedToast: {
      one: 'Cleared {count} item',
      other: 'Cleared {count} items',
    },
    clearError: 'Could not clear the bought items',
    quickAddRow: {
      placeholder: 'Add an item',
      nameLabel: 'Item name',
      amountPlaceholder: 'Amount',
      amountLabel: 'Amount',
      amountError: 'Enter a number greater than 0',
      unitLabel: 'Unit',
      add: 'Add',
    },
    itemRow: {
      markBought: 'Mark {name} bought',
      markNotBought: 'Mark {name} not bought',
      auto: 'Auto',
      urgent: 'Urgent',
      remove: 'Remove {name}',
    },
    generate: {
      title: 'Generate from low stock',
      cancel: 'Cancel',
      addToList: 'Add to list',
      checking: 'Checking stock…',
      nothingShort: 'Nothing is short.',
      new: 'New',
      raised: 'Raised',
      skipped: 'Skipped',
      addedToast: { one: 'Added {count} item', other: 'Added {count} items' },
      nothingToAdd: 'Nothing to add',
      checkError: 'Could not check low stock',
      generateError: 'Could not generate the list',
    },
  },
  gone: {
    title: 'Gone',
    howFarBack: 'How far back',
    windows: {
      sevenDays: '7 days',
      thirtyDays: '30 days',
      all: 'All',
    },
    thrownAway: 'Thrown away',
    finished: 'Finished',
    putItBack: 'Put it back',
    putBackAriaLabel: 'Put {name} back',
    putBackToast: 'Back in the kitchen · {name}',
    putBackError: 'Could not put {name} back',
    waste: {
      ariaLabel: 'Waste rate',
      notEnough: 'Not enough has gone in this window to show a rate yet.',
      trendHeading: 'Last 8 weeks',
      trendAriaLabel: 'Waste rate, last 8 weeks',
      trendTitleEmpty: '{week}: nothing gone',
      trendTitleCounted: '{week}: {discarded} of {total} ({percent} %)',
    },
    empty: 'Nothing has been thrown away or finished in this window.',
    showMore: 'Show more',
  },
  settings: {
    title: 'Settings',
    language: {
      heading: 'Display language',
      en: { name: 'English', hint: "Products' own names" },
      fi: { name: 'Suomi', hint: 'Finnish names where known' },
    },
    theme: {
      heading: 'Theme',
      system: { name: 'System', hint: 'Follow this device' },
      light: { name: 'Light', hint: 'Always light' },
      dark: { name: 'Dark', hint: 'Always dark' },
    },
  },
  // Post-MVP frontier item 13, phase 3 (round 2026-10-03-3): the receipt, scan and area
  // screens, plus the product search the receipt review row uses. Appended at the end, after
  // `settings`, so a sibling's keys added inside that block do not conflict with this namespace
  // list. Printed receipt text (the store's own line, its name and its amounts) is data, never
  // translated here - only the app's own words around it are.
  receipt: {
    title: 'Receipt',
    auditLink: 'Audit view',
    backToReceipts: 'Back to receipts',
    loading: 'Loading receipt',
    stillReading: 'Still reading this receipt… it usually takes about a minute.',
    notFound: 'Receipt not found.',
    notRead: 'This receipt could not be read.',
    readAgain: 'Read again',
    reprocessError: 'Could not queue this receipt',
    confirmedSummary: '{store}, {date}: already added to your stock.',
    methodOk: 'It was {label}.',
    methodNotOk: 'It was {label}, so names are as printed and nothing was categorised.',
    neverQueued: 'This receipt was never queued to be read.',
    unknownState: 'This receipt is in a state this app does not know: {status}.',
    readItNow: 'Read it now',
    itemsRead: {
      one: '{count} item read, {matched} already known',
      other: '{count} items read, {matched} already known',
    },
    readWithoutModel: 'Read without the AI model, so names are as printed.',
    readAgainWithModel: 'Read again with the model',
    pickCategory: 'Pick a category…',
    recoveredBadge: 'recovered',
    recoveredRawNeedsCategory: 'from the receipt text — pick a category',
    recoveredRaw: 'from the receipt text',
    completeness: {
      // Composed, not one sentence: `recovered` and `textLines` (when present) are
      // independent counts - "1 of 2 lines was …" has a plural noun (from the total) with a
      // singular verb (from the one recovered line) - so each piece picks its own form.
      countOfTotal: '{count} of {total}',
      lineNoun: { one: 'line', other: 'lines' },
      notRead: {
        one: 'was not read by the model — it is recovered below, please check it.',
        other: 'were not read by the model — they are recovered below, please check them.',
      },
      unaccounted: {
        one: '{count} line could not be read — see the receipt text.',
        other: '{count} lines could not be read — see the receipt text.',
      },
      mismatch:
        'The items add up to {sum} but the receipt total is {total} — something may be missing.',
      invalid: {
        one: "The model's answer had {count} unusable entry.",
        other: "The model's answer had {count} unusable entries.",
      },
    },
    missed: {
      heading: 'Add a missed item',
      nameLabel: 'Missed item name',
      categoryLabel: 'Missed item category',
      amountLabel: 'Missed item amount',
      unitLabel: 'Missed item unit',
      addToList: 'Add to list',
      incomplete: 'Finish the missed item or clear its name before confirming',
    },
    handAdded: {
      listLabel: 'Added by hand',
      suffix: 'added by hand',
      remove: 'Remove',
      removeAriaLabel: 'Remove {name}',
    },
    units: { pcs: 'pcs', g: 'g', dl: 'dl' },
    text: {
      show: 'Show receipt text',
      hide: 'Hide receipt text',
    },
    staleWarning:
      'This receipt is from {date} — expiry dates are counted from then, so most items ' +
      'will be added already expired.',
    skippedCount: '{count} skipped',
    nothingSkipped: 'Nothing skipped',
    show: 'Show',
    hide: 'Hide',
    household: {
      one: '{count} household item · ',
      other: '{count} household items · ',
    },
    dismiss: 'Dismiss receipt',
    addCount: { one: 'Add {count} item', other: 'Add {count} items' },
    toast: {
      dismissed: 'Dismissed · {store}',
      added: { one: 'Added {count} item · {store}', other: 'Added {count} items · {store}' },
      addError: 'Could not add these items',
    },
    itemRow: {
      include: 'Include {name}',
      change: 'Change',
      changeAriaLabel: 'Change {name}',
      productNameLabel: 'Product name',
      findExisting: 'Find existing product',
      findExistingAriaLabel: 'Find a product for {name}',
      newProduct: 'New product: {term}',
      reanalyse: 'Re-analyse',
      whatIsIt: 'What is it?',
      whatIsItPlaceholder: 'What is it? e.g. cashew nuts',
      askAgain: 'Ask again',
      reanalyseError: 'Could not re-analyse this line',
      confirmOverwrite:
        'This row has been edited by hand. Replace it with the re-analysed result?',
      needName: 'Give this product a name to include it',
      needCategory: 'Pick a category to include it',
    },
    provenance: {
      known: 'known',
      auto: 'auto',
    },
  },
  receipts: {
    list: {
      title: 'Receipts',
      scanLink: 'Scan a receipt',
      noItemsRead: 'No items read',
      noItemsYet: 'No items read yet',
      itemSummary: {
        one: '{count} item, {matched} already known',
        other: '{count} items, {matched} already known',
      },
      loadError: 'Could not load receipts.',
      emptyPrefix: 'No receipts yet. Share one to the Telegram bot, or',
      emptyScanLink: 'scan one here',
    },
    banner: {
      waiting: {
        one: '{count} receipt waiting to review',
        other: '{count} receipts waiting to review',
      },
      reading: { one: 'Reading a receipt…', other: 'Reading {count} receipts…' },
      failed: {
        one: 'A receipt could not be read',
        other: '{count} receipts could not be read',
      },
    },
    statusChip: {
      uploaded: 'Not read yet',
      queued: 'Waiting to be read',
      processing: 'Reading',
      completed: 'Waiting for review',
      failed: 'Could not read',
      confirmed: 'Added to stock',
    },
    audit: {
      title: 'Receipt audit',
      backToReceipts: 'Back to receipts',
      fileGone: 'The original file is no longer available.',
      pdfInline: 'This browser cannot show the PDF inline.',
      openOriginal: 'Open the original',
      scannedAlt: 'The scanned receipt',
      outcome: {
        stocked: 'Stocked',
        household: 'Household',
        skipped: 'Skipped',
        removed: 'Removed from stock',
        pending: 'Pending',
      },
      reanalysed: 'Re-analysed',
      hint: ' · hint: "{hint}"',
      linesHeading: 'Lines',
      noLines: 'No lines were read from this receipt.',
      unlinkedHeading: 'Also created from this receipt (line unknown)',
      aProduct: 'a product',
      ocrTextLabel: 'OCR text',
      modelAnswerLabel: "Model's answer",
      modelAnswerRetryLabel: "Model's answer (retry)",
      show: 'Show {label}',
      hide: 'Hide {label}',
      notFound: 'Receipt not found.',
      goToReview: 'Go to the review screen',
    },
  },
  scan: {
    title: 'Scan a receipt',
    fileLabel: 'Receipt',
    fileHint: 'A PDF e-receipt, a screenshot, or a photo of a paper one.',
    storeLabel: 'Store (optional)',
    storePlaceholder: 'Read from the receipt when left empty',
    dateLabel: 'Purchase date (optional)',
    upload: 'Upload',
    uploadError: 'Could not upload the receipt. Try again.',
  },
  area: {
    backToFridge: '← Fridge',
    notFound: 'No such part of the fridge.',
    nothingHere: 'Nothing here.',
  },
  productSearch: {
    label: 'Product',
    createNew: 'Create new: {term}',
    placeholder: 'Milk, ground beef, apples…',
  },
}

// Deliberately not `as const`: a literal type per string would make `fi.ts` a type error for
// every key whose Finnish text differs from the English one, which is all of them. Plain
// `string` (and `{ one: string; other: string }` for the plural pairs) is what lets `Messages`
// check *shape* - every key present, a plural pair where English has one - without pinning the
// value.
export type Messages = typeof en
