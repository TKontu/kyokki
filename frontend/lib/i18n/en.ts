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
    // Icon curation (operator ask 2026-10-03), shown only when the server has
    // ICON_CURATION_ENABLED set - the operator's own develop build, not every deployment.
    canonicalIcons: {
      heading: 'Canonical icons',
      empty: 'No icons marked yet',
      count: { one: '{count} icon marked', other: '{count} icons marked' },
      unmark: 'Unmark',
      downloadBundle: 'Download bundle',
    },
  },
}

// Deliberately not `as const`: a literal type per string would make `fi.ts` a type error for
// every key whose Finnish text differs from the English one, which is all of them. Plain
// `string` (and `{ one: string; other: string }` for the plural pairs) is what lets `Messages`
// check *shape* - every key present, a plural pair where English has one - without pinning the
// value.
export type Messages = typeof en
