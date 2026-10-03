/**
 * Finnish message catalogue (Post-MVP frontier item 13, phase 2).
 *
 * Typed against `en.ts` (`Messages = typeof en` in `lib/i18n/index.ts`), so a key missing
 * here - or shaped differently, e.g. a plain string where English has a `{one, other}` pair -
 * fails `tsc`; see `lib/i18n/__tests__` for the test that also asserts it at runtime.
 *
 * Plurals follow Finnish numeral agreement, not a word-for-word copy of the English one/other
 * split: a count of exactly one noun takes the nominative singular ("1 tuote"), and any other
 * count - including zero - takes the partitive singular ("3 tuotetta"), never the partitive
 * plural ("tuotteita") a bare, number-less plural would use. A negated sentence's object is
 * already partitive regardless of count (Finnish grammar, not this app's choice), so a few
 * "one"/"other" pairs below are identical text - that is correct, not an oversight.
 *
 * "English" and "Suomi" (the language choice's own option names) are endonyms: a language
 * names itself the same way whichever language the rest of the screen is in, the same reason a
 * French app's settings still offer "English", not a translation of it.
 */

import type { Messages } from './en'

export const fi: Messages = {
  shell: {
    nav: {
      main: 'Päävalikko',
      stock: 'Jääkaappi',
      shopping: 'Ostoslista',
      receipts: 'Kuitit',
      products: 'Tuotteet',
      gone: 'Käytetty',
      more: 'Lisää',
      settings: 'Asetukset',
    },
  },
  status: {
    retry: 'Yritä uudelleen',
    retryLabel: 'Yritä uudelleen: {label}',
    failed: '{label} epäonnistui',
    dismiss: 'Hylkää',
    dismissLabel: 'Hylkää: {label}',
    more: 'ja {count} muuta',
    unreachable: 'Ei yhteyttä keittiön palvelimeen',
    showingFrom: ' · näytetään varastotieto ajalta {when}',
    tryAgain: 'Yritä uudelleen',
    lastUpdated: 'Päivitetty viimeksi {when}',
  },
  common: {
    close: 'Sulje',
    tryAgain: 'Yritä uudelleen',
    keepMine: 'Pidä omani',
    useTheirs: 'Käytä {value}',
    fieldChangedWhileOpen: '{label} muuttui arvoon {value} tämän ollessa auki',
    cancel: 'Peruuta',
    add: 'Lisää',
    back: 'Takaisin',
    save: 'Tallenna',
    delete: 'Poista',
    location: 'Sijainti',
    expiry: 'Viimeinen käyttöpäivä',
    category: 'Kategoria',
  },
  errorScreen: {
    title: 'Jokin meni pieleen',
    body:
      'Kyokki kohtasi virheen, josta se ei selvinnyt itse. Se yrittää uudelleen itsekseen, ' +
      'niin että voit jättää tämän näytön rauhaan.',
    retry: 'Yritä uudelleen',
  },
  badge: {
    expiry: {
      expired: 'Vanhentunut',
      today: 'Tänään',
      days: '{count} pv',
      tenPlus: '10 pv+',
    },
    status: {
      sealed: 'Avaamaton',
      opened: 'Avattu',
      partial: 'Osittainen',
      empty: 'Tyhjä',
      discarded: 'Heitetty pois',
    },
  },
  fridge: {
    staleStrip: {
      heading: 'Vanhenemassa',
      ariaLabel: 'Vanhenemassa',
      clearExpired: 'Poista vanhentuneet',
      more: 'Lisää',
      allAriaLabel: 'Kaikki vanhenemassa olevat',
    },
    areaSpot: {
      empty: 'Tyhjä',
      open: 'Avaa {area}',
      moreInside: 'Lisää sisällä',
    },
  },
  home: {
    add: '+ Lisää',
  },
  inventory: {
    fridgeView: {
      loading: 'Ladataan varastoa',
      loadError: 'Varaston lataus epäonnistui.',
      empty:
        'Ei tuotteita. Lisää yksi + Lisää -painikkeesta, tai jaa kuitti Telegram-botille - ' +
        'voit myös skannata yhden Kuiteista.',
    },
    consumption: {
      usedUp: 'Käytetty loppuun',
      editItem: 'Muokkaa',
      usedUpToast: 'Käytetty loppuun · {name}',
      usedUpError: 'Kohteen {name} päivitys epäonnistui',
    },
    clearExpired: {
      title: {
        one: 'Poistetaanko {count} vanhentunut tuote?',
        other: 'Poistetaanko {count} vanhentunutta tuotetta?',
      },
      cancel: 'Peruuta',
      confirm: 'Kyllä, heitä pois',
      body:
        'Tämä kirjataan hävikiksi, mitä hävikkilaskuri seuraa. Jos söit jotain näistä, käytä ' +
        'sen omaa Käytetty loppuun -painiketta sen kortilla.',
      toast: {
        one: 'Heitetty pois · {count} tuote',
        other: 'Heitetty pois · {count} tuotetta',
      },
      error: {
        one: 'Ei voitu poistaa {count} tuotetta',
        other: 'Ei voitu poistaa {count} tuotetta',
      },
    },
    itemEdit: {
      cancel: 'Peruuta',
      confirmDelete: 'Kyllä, poista',
      deleteBody:
        'Poistetaanko {name}? Tämä poistaa kohteen; sen hävikki näkyy yhä Käytetty-sivulla. ' +
        'Jos se heitettiin pois, käytä Heitä pois -toimintoa.',
      save: 'Tallenna',
      markAsGone: 'Heitä pois',
      putItBack: 'Palauta',
      delete: 'Poista',
      addedOn: 'Lisätty {date}',
      fromLineAndText: 'Kuitti {store}, {date}: {line}',
      fromLine: 'Kuitti {store}, {date}',
      categoryLine: 'Kategoria: {category}',
      noCategory: 'Ei kategoriaa',
      change: 'Muuta…',
      changeProductDetails: 'Muuta tuotteen tietoja…',
      expiry: 'Viimeinen käyttöpäivä',
      location: 'Sijainti',
      loadingProductDetails: 'Ladataan tuotteen tietoja…',
      productDetailsError: 'Tuotteen {name} tietojen lataus epäonnistui.',
      backTo: 'Takaisin: {name}',
      freezerDateNote:
        'Tallennus antaa tälle pakastepäiväyksen. Jos otat sen myöhemmin pois pakastimesta, ' +
        'päiväys ei palaudu ennalleen — aseta se silloin itse.',
      freezerKeptNote: 'Antamasi päiväys säilyy, ei pakastimen omaa.',
      savedToast: 'Tallennettu · {name}',
      saveError: 'Kohteen {name} tallennus epäonnistui',
      deletedToast: 'Poistettu · {name}',
      deleteError: 'Kohteen {name} poisto epäonnistui',
      markedGoneToast: 'Heitetty pois · {name}',
      backInKitchenToast: 'Takaisin keittiössä · {name}',
    },
    quickAdd: {
      title: 'Lisää varastoon',
      newProduct: 'Uusi tuote',
      category: 'Kategoria',
      location: 'Sijainti',
      expiry: 'Viimeinen käyttöpäivä',
      back: 'Takaisin',
      add: 'Lisää',
      addedToast: 'Lisätty · {name}',
      addError: 'Kohteen {name} lisäys epäonnistui',
    },
    undo: {
      undo: 'Kumoa',
      undoDescribed: 'Kumoa {description}',
      error: 'Kumoaminen epäonnistui',
    },
  },
  shopping: {
    header: {
      title: 'Ostoslista',
      generate: 'Luo vähissä olevista',
    },
    empty: 'Listalla ei ole mitään.',
    groups: {
      urgent: 'Kiireelliset',
      normal: 'Normaalit',
      low: 'Ei kiireelliset',
      other: 'Muut',
    },
    bought: 'Ostetut ({count})',
    clearBought: 'Tyhjennä ostetut',
    boughtToast: 'Ostettu · {name}',
    undo: 'Kumoa',
    undoFailedToast: 'Kumoaminen epäonnistui; merkintä on yhä päällä',
    retry: 'Yritä uudelleen',
    updateError: 'Kohteen {name} päivitys epäonnistui',
    removeError: 'Kohteen {name} poisto epäonnistui',
    addError: 'Kohteen {name} lisäys epäonnistui',
    clearedToast: {
      one: 'Poistettu {count} kohde',
      other: 'Poistettu {count} kohdetta',
    },
    clearError: 'Ostettujen tyhjennys epäonnistui',
    quickAddRow: {
      placeholder: 'Lisää tuote',
      nameLabel: 'Tuotteen nimi',
      amountPlaceholder: 'Määrä',
      amountLabel: 'Määrä',
      amountError: 'Syötä nollaa suurempi luku',
      unitLabel: 'Yksikkö',
      add: 'Lisää',
    },
    itemRow: {
      markBought: 'Merkitse {name} ostetuksi',
      markNotBought: 'Merkitse {name} ostamattomaksi',
      auto: 'Autom.',
      urgent: 'Kiireellinen',
      remove: 'Poista {name}',
    },
    generate: {
      title: 'Luo vähissä olevista',
      cancel: 'Peruuta',
      addToList: 'Lisää listalle',
      checking: 'Tarkistetaan varastoa…',
      nothingShort: 'Mikään ei ole vähissä.',
      new: 'Uudet',
      raised: 'Korotetut',
      skipped: 'Ohitetut',
      addedToast: { one: 'Lisätty {count} kohde', other: 'Lisätty {count} kohdetta' },
      nothingToAdd: 'Ei lisättävää',
      checkError: 'Varastotilanteen tarkistus epäonnistui',
      generateError: 'Listan luonti epäonnistui',
    },
  },
  gone: {
    title: 'Käytetty',
    howFarBack: 'Kuinka pitkältä ajalta',
    windows: {
      sevenDays: '7 päivää',
      thirtyDays: '30 päivää',
      all: 'Kaikki',
    },
    thrownAway: 'Heitetty pois',
    finished: 'Käytetty loppuun',
    putItBack: 'Palauta',
    putBackAriaLabel: 'Palauta {name}',
    putBackToast: 'Takaisin keittiössä · {name}',
    putBackError: 'Kohteen {name} palautus epäonnistui',
    waste: {
      ariaLabel: 'Hävikkiprosentti',
      notEnough: 'Tällä aikavälillä ei ole tapahtunut tarpeeksi prosentin näyttämiseen.',
      trendHeading: 'Viimeiset 8 viikkoa',
      trendAriaLabel: 'Hävikkiprosentti, viimeiset 8 viikkoa',
      trendTitleEmpty: '{week}: ei mitään',
      trendTitleCounted: '{week}: {discarded}/{total} ({percent} %)',
    },
    empty: 'Mitään ei ole heitetty pois tai käytetty loppuun tällä aikavälillä.',
    showMore: 'Näytä lisää',
  },
  settings: {
    title: 'Asetukset',
    language: {
      heading: 'Näyttökieli',
      en: { name: 'English', hint: 'Tuotteiden omat nimet' },
      fi: { name: 'Suomi', hint: 'Suomenkieliset nimet, jos tiedossa' },
    },
    theme: {
      heading: 'Teema',
      system: { name: 'Järjestelmä', hint: 'Noudata laitteen asetusta' },
      light: { name: 'Vaalea', hint: 'Aina vaalea' },
      dark: { name: 'Tumma', hint: 'Aina tumma' },
    },
  },
  receipt: {
    title: 'Kuitti',
    auditLink: 'Tarkastusnäkymä',
    backToReceipts: 'Takaisin kuitteihin',
    loading: 'Ladataan kuittia',
    stillReading: 'Luetaan kuittia vielä… kestää yleensä noin minuutin.',
    notFound: 'Kuittia ei löytynyt.',
    notRead: 'Tätä kuittia ei voitu lukea.',
    readAgain: 'Yritä uudelleen',
    reprocessError: 'Kuitin jonotus epäonnistui',
    confirmedSummary: '{store}, {date}: lisätty jo varastoon.',
    methodOk: 'Tämä on {label}.',
    methodNotOk: 'Tämä on {label}, joten nimet ovat kuitin mukaisia eikä mitään luokiteltu.',
    neverQueued: 'Tätä kuittia ei ole koskaan jonotettu luettavaksi.',
    unknownState: 'Tämä kuitti on tilassa, jota sovellus ei tunne: {status}.',
    readItNow: 'Lue nyt',
    itemsRead: {
      one: '{count} tuote luettu, {matched} jo tiedossa',
      other: '{count} tuotetta luettu, {matched} jo tiedossa',
    },
    readWithoutModel: 'Luettu ilman tekoälymallia, joten nimet ovat kuitin mukaisia.',
    readAgainWithModel: 'Lue uudelleen mallilla',
    pickCategory: 'Valitse kategoria…',
    recoveredBadge: 'palautettu',
    recoveredRawNeedsCategory: 'kuitin tekstistä — valitse kategoria',
    recoveredRaw: 'kuitin tekstistä',
    completeness: {
      countOfTotal: '{count}/{total}',
      lineNoun: { one: 'rivi', other: 'riviä' },
      notRead: {
        one: 'jäi lukematta mallilta — se on palautettu alla, tarkista se.',
        other: 'jäi lukematta mallilta — ne on palautettu alla, tarkista ne.',
      },
      unaccounted: {
        one: '{count} rivi jäi lukematta — katso kuitin teksti.',
        other: '{count} riviä jäi lukematta — katso kuitin teksti.',
      },
      mismatch:
        'Tuotteet ovat yhteensä {sum}, mutta kuitin loppusumma on {total} — jotain saattaa puuttua.',
      invalid: {
        one: 'Mallin vastauksessa oli {count} käyttökelvoton rivi.',
        other: 'Mallin vastauksessa oli {count} käyttökelvotonta riviä.',
      },
    },
    missed: {
      heading: 'Lisää puuttuva tuote',
      nameLabel: 'Puuttuvan tuotteen nimi',
      categoryLabel: 'Puuttuvan tuotteen kategoria',
      amountLabel: 'Puuttuvan tuotteen määrä',
      unitLabel: 'Puuttuvan tuotteen yksikkö',
      addToList: 'Lisää listalle',
      incomplete: 'Täydennä puuttuva tuote tai tyhjennä sen nimi ennen vahvistusta',
    },
    handAdded: {
      listLabel: 'Lisätty käsin',
      suffix: 'lisätty käsin',
      remove: 'Poista',
      removeAriaLabel: 'Poista {name}',
    },
    units: { pcs: 'kpl', g: 'g', dl: 'dl' },
    text: {
      show: 'Näytä kuitin teksti',
      hide: 'Piilota kuitin teksti',
    },
    staleWarning:
      'Tämä kuitti on päivätty {date} — viimeiset käyttöpäivät lasketaan siitä, joten ' +
      'useimmat tuotteet lisätään jo vanhentuneina.',
    skippedCount: '{count} ohitettu',
    nothingSkipped: 'Ei ohituksia',
    show: 'Näytä',
    hide: 'Piilota',
    household: {
      one: '{count} kotitaloustuote · ',
      other: '{count} kotitaloustuotetta · ',
    },
    dismiss: 'Hylkää kuitti',
    addCount: { one: 'Lisää {count} tuote', other: 'Lisää {count} tuotetta' },
    toast: {
      dismissed: 'Hylätty · {store}',
      added: {
        one: 'Lisätty {count} tuote · {store}',
        other: 'Lisätty {count} tuotetta · {store}',
      },
      addError: 'Tuotteiden lisäys epäonnistui',
    },
    itemRow: {
      include: 'Sisällytä {name}',
      change: 'Muuta',
      changeAriaLabel: 'Muuta: {name}',
      productNameLabel: 'Tuotteen nimi',
      findExisting: 'Etsi olemassa oleva tuote',
      findExistingAriaLabel: 'Etsi tuote: {name}',
      newProduct: 'Uusi tuote: {term}',
      reanalyse: 'Analysoi uudelleen',
      whatIsIt: 'Mikä tämä on?',
      whatIsItPlaceholder: 'Mikä tämä on? esim. cashewpähkinät',
      askAgain: 'Kysy uudelleen',
      reanalyseError: 'Rivin uudelleenanalyysi epäonnistui',
      confirmOverwrite:
        'Tätä riviä on muokattu käsin. Korvataanko se uudelleenanalyysin tuloksella?',
      needName: 'Anna tälle tuotteelle nimi sisällyttääksesi sen',
      needCategory: 'Valitse kategoria sisällyttääksesi sen',
    },
    provenance: {
      known: 'tiedossa',
      auto: 'arvio',
    },
  },
  receipts: {
    list: {
      title: 'Kuitit',
      scanLink: 'Skannaa kuitti',
      noItemsRead: 'Ei luettuja tuotteita',
      noItemsYet: 'Ei vielä luettuja tuotteita',
      itemSummary: {
        one: '{count} tuote luettu, {matched} jo tiedossa',
        other: '{count} tuotetta luettu, {matched} jo tiedossa',
      },
      loadError: 'Kuittien lataus epäonnistui.',
      emptyPrefix: 'Ei kuitteja vielä. Jaa yksi Telegram-botille tai',
      emptyScanLink: 'skannaa yksi tässä',
    },
    banner: {
      waiting: {
        one: '{count} kuitti odottaa tarkistusta',
        other: '{count} kuittia odottaa tarkistusta',
      },
      reading: { one: 'Luetaan kuittia…', other: 'Luetaan {count} kuittia…' },
      failed: {
        one: 'Kuittia ei voitu lukea',
        other: '{count} kuittia ei voitu lukea',
      },
    },
    statusChip: {
      uploaded: 'Ei vielä luettu',
      queued: 'Odottaa lukemista',
      processing: 'Luetaan',
      completed: 'Odottaa tarkistusta',
      failed: 'Ei voitu lukea',
      confirmed: 'Lisätty varastoon',
    },
    audit: {
      title: 'Kuitin tarkastus',
      backToReceipts: 'Takaisin kuitteihin',
      fileGone: 'Alkuperäinen tiedosto ei ole enää saatavilla.',
      pdfInline: 'Tämä selain ei voi näyttää PDF-tiedostoa upotettuna.',
      openOriginal: 'Avaa alkuperäinen',
      scannedAlt: 'Skannattu kuitti',
      outcome: {
        stocked: 'Lisätty varastoon',
        household: 'Kotitaloustuote',
        skipped: 'Ohitettu',
        removed: 'Poistettu varastosta',
        pending: 'Odottaa',
      },
      reanalysed: 'Analysoitu uudelleen',
      hint: ' · vihje: "{hint}"',
      linesHeading: 'Rivit',
      noLines: 'Tältä kuitilta ei luettu rivejä.',
      unlinkedHeading: 'Myös luotu tästä kuitista (rivi tuntematon)',
      aProduct: 'tuote',
      ocrTextLabel: 'OCR-teksti',
      modelAnswerLabel: 'Mallin vastaus',
      modelAnswerRetryLabel: 'Mallin vastaus (uusinta)',
      show: 'Näytä {label}',
      hide: 'Piilota {label}',
      notFound: 'Kuittia ei löytynyt.',
      goToReview: 'Siirry tarkistusnäkymään',
    },
  },
  scan: {
    title: 'Skannaa kuitti',
    fileLabel: 'Kuitti',
    fileHint: 'PDF-kuitti, kuvakaappaus tai valokuva paperikuitista.',
    storeLabel: 'Kauppa (valinnainen)',
    storePlaceholder: 'Luetaan kuitista, jos jätetään tyhjäksi',
    dateLabel: 'Ostopäivä (valinnainen)',
    upload: 'Lähetä',
    uploadError: 'Kuitin lähetys epäonnistui. Yritä uudelleen.',
  },
  area: {
    backToFridge: '← Jääkaappi',
    notFound: 'Tällaista jääkaapin osaa ei ole.',
    nothingHere: 'Täällä ei ole mitään.',
  },
  productSearch: {
    label: 'Tuote',
    createNew: 'Luo uusi: {term}',
    placeholder: 'Maito, jauheliha, omenat…',
  },
}
