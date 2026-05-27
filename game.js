(async () => {
  const GAME_WIDTH = 720;
  const GAME_HEIGHT = 960;
  const BATCH_SIZE = 3;
  const BUTTON_SIZE = 82;
  const OUT_DISTANCE = 164;
  const STEP_DELAY = 120;
  const ROOM_IMAGE_ROOT = "images/rooms";
  const CHARACTER_IMAGE_ROOT = "images/characters";
  const ATLAS_ROOT = "images/atlases";
  const CHARACTER_CONFIG_URL = "config/characters.json";
  const TEXT_RU_URL = "config/text/ru.json";
  const TRANSPARENT_PIXEL_DATA_URL = "data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///ywAAAAAAQABAAACAUwAOw==";
  const SPRITE_Z = {
    SURFACE_DAMAGE: 1000,
    FLOOR_COVERING: 2000,
    WALL_FIXTURE: 3000,
    LOOSE_OBJECT: 4000
  };

  const TRIGGER_OPTIONS = [
    { value: "on_room_enter", label: "on_room_enter" },
    { value: "on_room_finished", label: "on_room_finished" },
    { value: "before_action", label: "before_action" },
    { value: "after_action", label: "after_action" },
    { value: "levelCompleted", label: "levelCompleted" }
  ];
  const PHASE_OPTIONS = [
    { value: "", label: "Любой" },
    { value: "repair", label: "Ремонт/мусор" },
    { value: "decor", label: "Декор" }
  ];
  const POSITION_OPTIONS = [
    { value: "left", label: "Слева" },
    { value: "right", label: "Справа" }
  ];
  const DEFAULT_CHARACTER_NAMES = {
    "images/characters/anna/anna_neutral.png": "Анна",
    "images/characters/anna/anna_smile.png": "Анна",
    "images/characters/anna/anna_sad.png": "Анна",
    "images/characters/anna/anna_fear.png": "Анна",
    "images/characters/anna/anna_angry.png": "Анна",
    "images/characters/anna/anna_embarrassed.png": "Анна",
    "images/characters/alex/alex_neutral.png": "Алекс",
    "images/characters/alex/alex_joy.png": "Алекс",
    "images/characters/alex/alex_sad.png": "Алекс",
    "images/characters/alex/alex_angry.png": "Алекс",
    "images/characters/victor/victor_neutral.png": "Виктор",
    "images/characters/victor/victor_smirk.png": "Виктор",
    "images/characters/mary/mary_neutral.png": "Тетя Мэри",
    "images/characters/mary/mary_smile.png": "Тетя Мэри",
    "images/characters/henry/henry_neutral.png": "Генри",
    "images/characters/henry/henry_smile.png": "Генри",
    "images/characters/henry/henry_embarrassed.png": "Генри",
    "images/characters/kate/kate_neutral.png": "Кейт",
    "images/characters/kate/kate_smile.png": "Кейт",
    "images/characters/kate/kate_smirk.png": "Кейт",
    "images/characters/kate/kate_angry.png": "Кейт"
  };

  const shell = document.querySelector("#game-shell");
  const game = document.querySelector("#game");
  const roomBg = document.querySelector("#room-bg");
  const itemsLayer = document.querySelector("#items");
  const actionsLayer = document.querySelector("#actions");
  const status = document.querySelector("#status");
  const topMenuButton = document.querySelector("#top-menu-button");
  const roomMenu = document.querySelector("#room-menu");
  const roomList = document.querySelector("#room-list");
  const menuTitle = document.querySelector("#menu-title");
  const roomsTab = document.querySelector("#rooms-tab");
  const dialogsTab = document.querySelector("#dialogs-tab");
  const roomsView = document.querySelector("#rooms-view");
  const dialogEditorView = document.querySelector("#dialog-editor-view");
  const editorRoomIndex = document.querySelector("#editor-room-index");
  const dialogAdd = document.querySelector("#dialog-add");
  const dialogExport = document.querySelector("#dialog-export");
  const dialogExportOutput = document.querySelector("#dialog-export-output");
  const dialogList = document.querySelector("#dialog-list");
  const dialogForm = document.querySelector("#dialog-form");
  const dialogIdInput = document.querySelector("#dialog-id");
  const dialogRoomIndexInput = document.querySelector("#dialog-room-index");
  const conditionAdd = document.querySelector("#condition-add");
  const conditionList = document.querySelector("#condition-list");
  const lineAdd = document.querySelector("#line-add");
  const lineList = document.querySelector("#line-list");
  const dialogSave = document.querySelector("#dialog-save");
  const dialogDelete = document.querySelector("#dialog-delete");
  const variantPanel = document.querySelector("#variant-panel");
  const variantOptions = document.querySelector("#variant-options");
  const variantChoose = document.querySelector("#variant-choose");
  const variantClose = document.querySelector("#variant-close");
  const dialogOverlay = document.querySelector("#dialog-overlay");
  const dialogCharacterLeft = document.querySelector("#dialog-character-left");
  const dialogCharacterRight = document.querySelector("#dialog-character-right");
  const dialogSpeaker = document.querySelector("#dialog-speaker");
  const dialogText = document.querySelector("#dialog-text");
  const dialogNext = document.querySelector("#dialog-next");
  const levelTest = document.querySelector("#level-test");
  const levelDown = document.querySelector("#level-down");
  const levelUp = document.querySelector("#level-up");
  const levelValue = document.querySelector("#level-value");

  let roomDescriptors = [];
  let currentRoomId = null;
  let currentRoomIndex = 0;
  let orders = { repair: [], decor: [] };
  let phaseByGroup = new Map();
  let actionPointsByGroup = new Map();
  let currentRoomAtlas = null;
  let characterAtlas = null;
  let sprites = [];
  let state = createInitialState();
  let activeVariant = null;
  let dialogsConfig = normalizeDialogsConfig({});
  let editorDraft = null;
  let editorSelectedId = null;
  let activeDialogPlayback = null;
  let activeRoomDialogs = [];
  let dialogQueue = [];
  let playedDialogKeys = new Set();
  let levelIndex = 0;

  syncScale();
  window.addEventListener("resize", syncScale);
  topMenuButton.addEventListener("click", showMenu);
  roomsTab.addEventListener("click", () => showMenuView("rooms"));
  dialogsTab?.addEventListener("click", () => showMenuView("dialogs"));
  editorRoomIndex.addEventListener("change", handleEditorRoomChange);
  dialogAdd.addEventListener("click", createDialogDraft);
  dialogExport.addEventListener("click", exportDialogsConfig);
  dialogForm.addEventListener("submit", saveDialogDraft);
  dialogDelete.addEventListener("click", deleteSelectedDialog);
  conditionAdd.addEventListener("click", addConditionToDraft);
  lineAdd.addEventListener("click", addLineToDraft);
  variantChoose.addEventListener("click", chooseVariant);
  variantClose.addEventListener("click", closeVariantPicker);
  dialogNext.addEventListener("click", advanceDialog);
  levelDown.addEventListener("click", () => changeLevel(-1));
  levelUp.addEventListener("click", () => changeLevel(1));

  topMenuButton.classList.add("hidden");
  levelTest.classList.add("hidden");

  const [rooms, loadedCharacters, loadedDialogTexts] = await Promise.all([
    loadRooms(),
    loadCharactersConfig(),
    loadDialogTexts()
  ]);
  roomDescriptors = rooms;
  dialogsConfig = normalizeDialogsConfig(loadedCharacters, loadedDialogTexts);
  characterAtlas = await loadCharacterAtlas(dialogsConfig);
  editorRoomIndex.value = String(initialRoomIndex(roomDescriptors));
  renderRoomMenu(roomDescriptors);
  renderDialogList();
  showMenuView("rooms");

  async function loadRooms() {
    try {
      const response = await fetch("config/rooms.json");
      if (!response.ok) {
        throw new Error("rooms manifest not found");
      }

      const manifest = await response.json();
      if (Array.isArray(manifest.rooms) && manifest.rooms.length > 0) {
        return manifest.rooms;
      }
    } catch (error) {
      return discoverRooms();
    }

    return discoverRooms();
  }

  async function discoverRooms() {
    const rooms = [];
    let misses = 0;

    for (let number = 1; number <= 50 && misses < 3; number += 1) {
      if (await roomExists(number)) {
        rooms.push({ id: `room${number}`, number });
        misses = 0;
      } else if (rooms.length > 0) {
        misses += 1;
      }
    }

    return rooms.length > 0 ? rooms : [{ id: "room1", number: 1 }];
  }

  async function roomExists(number) {
    try {
      const response = await fetch(`config/room${number}.json`, { method: "HEAD" });
      return response.ok;
    } catch (error) {
      return false;
    }
  }

  async function loadCharactersConfig() {
    try {
      const response = await fetch(CHARACTER_CONFIG_URL, { cache: "no-store" });
      if (!response.ok) {
        throw new Error("characters config not found");
      }

      return response.json();
    } catch (error) {
      return createDefaultDialogsConfig();
    }
  }

  async function loadDialogTexts() {
    const ru = await loadJsonOrNull(TEXT_RU_URL);
    return ru ?? {};
  }

  async function loadJsonOrNull(url) {
    try {
      const response = await fetch(url, { cache: "no-store" });
      if (!response.ok) {
        throw new Error(`${url} not found`);
      }

      return response.json();
    } catch (error) {
      return null;
    }
  }

  async function loadRoomAtlas(roomId) {
    const phaseAtlas = await loadAtlasGroup([
      `rooms_${roomId}-repair`,
      `rooms_${roomId}-decor`
    ]);
    if (phaseAtlas !== null) {
      return phaseAtlas;
    }

    return loadAtlasGroup([`rooms_${roomId}`]);
  }

  async function loadCharacterAtlas(config) {
    return loadAtlasGroup(characterAtlasBases(config));
  }

  function characterAtlasBases(config) {
    const ids = new Set();

    for (const character of config.characters ?? []) {
      const id = String(character.id ?? "").trim();
      if (id) {
        ids.add(id);
      }
    }

    for (const image of Object.keys(config.characterNames ?? DEFAULT_CHARACTER_NAMES)) {
      const id = characterIdFromState(characterStateFromImage(image));
      if (id) {
        ids.add(id);
      }
    }

    return [...ids].sort().map((id) => `characters_${atlasSafeName(id)}`);
  }

  async function loadAtlasGroup(atlasBases) {
    const frames = {};

    for (const atlasBase of atlasBases) {
      const atlas = await loadAtlasByBase(atlasBase);
      if (atlas !== null) {
        Object.assign(frames, atlas.frames);
      }
    }

    return Object.keys(frames).length > 0 ? { frames } : null;
  }

  async function loadAtlasByBase(atlasBase) {
    const atlasUrls = [
      `${ATLAS_ROOT}/${atlasBase}.webp.json`,
      `${ATLAS_ROOT}/${atlasBase}.json`
    ];

    for (const atlasUrl of atlasUrls) {
      const atlas = await loadJsonOrNull(atlasUrl);
      const normalized = normalizeAtlas(atlas);
      if (normalized !== null) {
        return normalized;
      }
    }

    return null;
  }

  function normalizeAtlas(atlas) {
    if (!atlas || typeof atlas !== "object") {
      return null;
    }

    if (Array.isArray(atlas.pages)) {
      return normalizeMultiPageAtlas(atlas.pages);
    }

    if (!atlas.frames || typeof atlas.frames !== "object") {
      return null;
    }

    const image = String(atlas.meta?.image ?? "").trim();
    const width = toFiniteNumber(atlas.meta?.size?.w, 0);
    const height = toFiniteNumber(atlas.meta?.size?.h, 0);
    if (!image || width <= 0 || height <= 0) {
      return null;
    }

    return normalizeSinglePageAtlas({
      frames: atlas.frames,
      image,
      width,
      height
    });
  }

  function normalizeMultiPageAtlas(pages) {
    const frames = {};

    for (const page of pages) {
      if (!page || typeof page !== "object" || !page.frames || typeof page.frames !== "object") {
        continue;
      }

      const image = String(page.image ?? "").trim();
      const width = toFiniteNumber(page.size?.w, 0);
      const height = toFiniteNumber(page.size?.h, 0);
      if (!image || width <= 0 || height <= 0) {
        continue;
      }

      Object.assign(frames, normalizeAtlasFrames(page.frames, image, width, height));
    }

    return Object.keys(frames).length > 0 ? { frames } : null;
  }

  function normalizeSinglePageAtlas(page) {
    return {
      frames: normalizeAtlasFrames(page.frames, page.image, page.width, page.height)
    };
  }

  function normalizeAtlasFrames(rawFrames, image, width, height) {
    const frames = {};
    for (const [key, frame] of Object.entries(rawFrames)) {
      if (!frame || typeof frame !== "object" || !frame.frame) {
        continue;
      }

      frames[key] = {
        ...frame,
        atlasImageUrl: `${ATLAS_ROOT}/${image}`,
        atlasWidth: width,
        atlasHeight: height
      };
    }

    return frames;
  }

  function renderRoomMenu(rooms) {
    roomList.replaceChildren();

    for (const room of rooms) {
      const button = document.createElement("button");
      button.className = "room-button";
      button.type = "button";
      button.textContent = room.title ?? `Комната ${room.number ?? roomIndexFromId(room.id)}`;
      button.addEventListener("click", () => startRoom(room));
      roomList.appendChild(button);
    }
  }

  async function startRoom(room) {
    currentRoomId = room.id;
    currentRoomIndex = toPositiveInt(room.number ?? roomIndexFromId(room.id), 1);
    state = createInitialState();
    activeVariant = null;
    orders = { repair: [], decor: [] };
    phaseByGroup = new Map();
    actionPointsByGroup = new Map();
    sprites = [];
    activeRoomDialogs = [];
    playedDialogKeys = new Set();
    levelIndex = 0;

    updateLevelCounter();
    itemsLayer.replaceChildren();
    actionsLayer.replaceChildren();
    hideVariantPanel();
    closeDialogPlayback();

    roomMenu.classList.add("hidden");
    topMenuButton.classList.remove("hidden");
    levelTest.classList.add("hidden");
    status.textContent = "";

    const roomConfig = await fetch(`config/${currentRoomId}.json`).then((response) => response.json());
    const orderConfig = roomConfig.content ? null : await loadLegacyRoomOrder(currentRoomId);

    currentRoomAtlas = await loadRoomAtlas(currentRoomId);
    applyRoomImage(roomBg, roomBackgroundImageId(roomConfig));
    orders = normalizeRoomOrders(roomConfig, orderConfig);
    phaseByGroup = buildPhaseMap(orders);
    actionPointsByGroup = buildActionPointMap(roomConfig);
    sprites = createSprites(roomConfig);
    activeRoomDialogs = normalizeRoomDialogs(roomConfig);

    showNextBatch();
    triggerDialogs("on_room_enter", {
      triggerKey: currentRoomId,
      roomId: currentRoomId
    });
  }

  function showMenu() {
    currentRoomId = null;
    currentRoomIndex = 0;
    state = createInitialState();
    activeVariant = null;
    currentRoomAtlas = null;
    activeRoomDialogs = [];
    itemsLayer.replaceChildren();
    actionsLayer.replaceChildren();
    hideVariantPanel();
    closeDialogPlayback();
    clearRoomImage(roomBg);
    roomMenu.classList.remove("hidden");
    topMenuButton.classList.add("hidden");
    levelTest.classList.add("hidden");
    status.textContent = "";
    showMenuView("rooms");
  }

  function showMenuView(view) {
    const isDialogs = view === "dialogs";
    roomsView.classList.toggle("hidden", isDialogs);
    dialogEditorView.classList.toggle("hidden", !isDialogs);
    roomsTab.classList.toggle("selected", !isDialogs);
    dialogsTab?.classList.toggle("selected", isDialogs);
    menuTitle.textContent = isDialogs ? "Редактор диалогов" : "Выбор комнаты";

    if (isDialogs) {
      renderDialogList();
      renderDialogForm();
    }
  }

  function createInitialState() {
    return {
      phase: "repair",
      cursor: 0,
      batch: [],
      busy: false
    };
  }

  function createSprites(roomConfig) {
    return flattenRoomObjects(roomConfig)
      .map((object, index) => {
        const phase = phaseByGroup.get(object.group);
        if (phase === undefined) {
          return null;
        }

        const imageId = object.imageId ?? object.id;
        const element = createRoomImageElement(imageId);
        element.className = "sprite";
        element.dataset.id = object.id;
        element.dataset.imageId = imageId;
        element.dataset.group = object.group;
        element.dataset.phase = phase;
        applySpriteSize(element, object);
        positionSpriteElement(element, object);
        element.style.zIndex = String(spriteZIndex(object, index, phase));

        if (phase === "decor") {
          element.classList.add("hidden");
          element.style.opacity = "0";
        } else {
          element.style.opacity = "1";
        }

        itemsLayer.appendChild(element);
        return {
          ...object,
          phase,
          order: index,
          variant: object.variant ?? variantFromId(object.id),
          element,
          done: phase === "decor"
        };
      })
      .filter(Boolean);
  }

  function applySpriteSize(element, object) {
    if (Number.isFinite(object.width)) {
      element.style.width = `${object.width}px`;
    }

    if (Number.isFinite(object.height)) {
      element.style.height = `${object.height}px`;
    }
  }

  function positionSpriteElement(element, object) {
    const size = spriteRenderSize(element, object);
    const left = object.coordinates === "center" ? object.x - size.width / 2 : object.x;
    const top = object.coordinates === "center" ? object.y - size.height / 2 : object.y;

    element.style.left = `${left}px`;
    element.style.top = `${top}px`;

    if (element instanceof HTMLImageElement && (size.width <= 0 || size.height <= 0)) {
      element.addEventListener("load", () => positionSpriteElement(element, object), { once: true });
    }
  }

  function spriteRenderSize(element, object) {
    return {
      width: Number.isFinite(object.width) ? object.width : stylePixelValue(element.style.width) || naturalImageDimension(element, "width"),
      height: Number.isFinite(object.height) ? object.height : stylePixelValue(element.style.height) || naturalImageDimension(element, "height")
    };
  }

  function naturalImageDimension(element, axis) {
    if (!(element instanceof HTMLImageElement)) {
      return 0;
    }

    return axis === "width" ? element.naturalWidth : element.naturalHeight;
  }

  function stylePixelValue(value) {
    const number = Number.parseFloat(value);
    return Number.isFinite(number) ? number : 0;
  }

  function flattenRoomObjects(roomConfig) {
    if (Array.isArray(roomConfig.allParts) && Array.isArray(roomConfig.allMultiobjects)) {
      const partsByKey = new Map(
        roomConfig.allParts
          .filter((part) => part && typeof part === "object")
          .map((part) => [String(part.key), part])
      );
      const actionPoints = Array.isArray(roomConfig.allActionPoints) ? roomConfig.allActionPoints : [];
      const actionByMultiobject = new Map();

      for (const actionPoint of actionPoints) {
        if (!actionPoint || typeof actionPoint !== "object" || !Array.isArray(actionPoint.multiobjects)) {
          continue;
        }

        for (const multiobjectKey of actionPoint.multiobjects) {
          actionByMultiobject.set(String(multiobjectKey), String(actionPoint.key));
        }
      }

      return roomConfig.allMultiobjects.flatMap((multiobject) => {
        if (!multiobject || typeof multiobject !== "object" || !Array.isArray(multiobject.parts)) {
          return [];
        }

        const multiobjectKey = String(multiobject.key);
        const group = actionByMultiobject.get(multiobjectKey) ?? String(multiobject.actionPoint ?? multiobject.group ?? multiobjectKey);
        const actionPoint = actionPoints.find((item) => item && String(item.key) === group);
        const variant = variantForMultiobject(actionPoint, multiobjectKey);
        const price = normalizePriceValue(multiobject.price);

        return multiobject.parts
          .map((partKey) => partsByKey.get(String(partKey)))
          .filter(Boolean)
          .map((part) => ({
            id: String(part.key),
            imageId: String(part.image ?? part.imageId ?? part.key),
            group,
            multiobject: multiobjectKey,
            price,
            x: toFiniteNumber(part.x, 0),
            y: toFiniteNumber(part.y, 0),
            width: toFiniteNumber(part.width, toFiniteNumber(multiobject.width, null)),
            height: toFiniteNumber(part.height, toFiniteNumber(multiobject.height, null)),
            angle: toFiniteNumber(part.angle, toFiniteNumber(multiobject.angle, 0)),
            variant,
            coordinates: "center"
          }));
      });
    }

    if (Array.isArray(roomConfig.groups)) {
      return roomConfig.groups.flatMap((group) => {
        return group.objects.map((object) => ({
          ...object,
          group: group.groupId ?? group.id,
          coordinates: "topLeft"
        }));
      });
    }

    return (roomConfig.objects ?? []).map((object) => ({
      ...object,
      imageId: object.imageId ?? object.id,
      angle: object.angle ?? angleFromId(object.id),
      coordinates: "topLeft"
    }));
  }

  async function loadLegacyRoomOrder(roomId) {
    try {
      const response = await fetch(`config/${roomId}_order.json`);
      if (!response.ok) {
        throw new Error("legacy room order not found");
      }

      return response.json();
    } catch (error) {
      return { repair: [], decor: [] };
    }
  }

  function normalizeRoomOrders(roomConfig, orderConfig) {
    if (roomConfig.content && typeof roomConfig.content === "object") {
      return {
        repair: normalizeOrder(roomConfig.content.repairActionPoint),
        decor: normalizeOrder(roomConfig.content.decorActionPoint)
      };
    }

    return {
      repair: normalizeOrder(orderConfig?.repair),
      decor: normalizeOrder(orderConfig?.decor)
    };
  }

  function roomBackgroundImageId(roomConfig) {
    return String(roomConfig.background ?? roomConfig.backgroundImage ?? `${currentRoomId}_room_bg`);
  }

  function normalizeRoomDialogs(roomConfig) {
    const rawDialogs = Array.isArray(roomConfig.dialogs) ? roomConfig.dialogs : null;
    if (rawDialogs !== null) {
      return rawDialogs.map((dialog, index) => normalizeDialogItem(dialog, index, {
        characterStateKeys: dialogsConfig.characterStateKeys,
        dialogTexts: dialogsConfig.dialogTexts,
        roomId: currentRoomId,
        roomIndex: currentRoomIndex
      })).filter(Boolean);
    }

    return dialogsConfig.dialogs.filter((dialog) => dialog.roomIndex === currentRoomIndex);
  }

  function buildActionPointMap(roomConfig) {
    const map = new Map();
    if (!Array.isArray(roomConfig.allActionPoints)) {
      return map;
    }

    for (const actionPoint of roomConfig.allActionPoints) {
      if (!actionPoint || typeof actionPoint !== "object" || !actionPoint.key) {
        continue;
      }

      map.set(String(actionPoint.key), actionPoint);
    }

    return map;
  }

  function normalizeOrder(entries = []) {
    return entries.map((entry) => {
      if (typeof entry === "string") {
        const curly = entry.match(/\{(-?\d+)\}$/);
        const square = entry.match(/\[(-?\d+)\]$/);
        const angleMatch = curly ?? square;
        return {
          group: normalizeActionKey(entry),
          angle: angleMatch ? Number(angleMatch[1]) : null,
          done: false
        };
      }

      return {
        group: normalizeActionKey(entry.group ?? entry.id ?? entry.key ?? ""),
        angle: Number.isFinite(entry.angle) ? entry.angle : null,
        done: false
      };
    });
  }

  function normalizeActionKey(value) {
    const raw = String(value).trim().replace(/\{(-?\d+)\}$/, "").replace(/\[(-?\d+)\]$/, "");
    return raw.startsWith(`${currentRoomId}_`) ? raw : normalizeGroup(raw);
  }

  function normalizeGroup(value) {
    return String(value)
      .replace(/\{(-?\d+)\}$/, "")
      .replace(/\[(-?\d+)\]$/, "")
      .replace(/_(?:[A-Z])(?:_\d+)?$/, "")
      .replace(/_\d+$/, "");
  }

  function buildPhaseMap(normalizedOrders) {
    const map = new Map();

    for (const action of normalizedOrders.repair) {
      map.set(action.group, "repair");
    }

    for (const action of normalizedOrders.decor) {
      map.set(action.group, "decor");
    }

    return map;
  }

  function angleFromId(id) {
    const match = id.trim().match(/\[(-?\d+)\]$/);
    return match ? Number(match[1]) : 0;
  }

  function angleForObject(object) {
    return Number.isFinite(object.angle) ? object.angle : angleFromId(object.id);
  }

  function idWithoutAngle(id) {
    return id.trim().replace(/\[(-?\d+)\]$/, "");
  }

  function variantFromId(id) {
    const match = idWithoutAngle(id).match(/_([A-Z])(?:_\d+)?$/);
    return match ? match[1] : null;
  }

  function variantForMultiobject(actionPoint, multiobjectKey) {
    if (!actionPoint || !Array.isArray(actionPoint.multiobjects) || actionPoint.multiobjects.length <= 1) {
      return null;
    }

    const index = actionPoint.multiobjects.map(String).indexOf(String(multiobjectKey));
    if (index < 0) {
      return null;
    }

    return String.fromCharCode("A".charCodeAt(0) + index);
  }

  function naturalIndex(id) {
    const match = idWithoutAngle(id).match(/_(\d+)$/);
    return match ? Number(match[1]) : Number.POSITIVE_INFINITY;
  }

  function spriteZIndex(object, index, phase) {
    return spriteZBase(object, phase) + index;
  }

  function spriteZBase(object, phase) {
    if (phase === "repair" && spriteKeyMatches(object, /(?:^|_)broken_(?:wall|floor)(?:_|$)/)) {
      return SPRITE_Z.SURFACE_DAMAGE;
    }

    if (spriteKeyMatches(object, /(?:^|_)(?:carpet|rug)(?:_|$)/)) {
      return SPRITE_Z.FLOOR_COVERING;
    }

    if (spriteKeyMatches(object, /(?:^|_)(?:trash|plant|chair)(?:_|$)/)) {
      return SPRITE_Z.LOOSE_OBJECT;
    }

    return SPRITE_Z.WALL_FIXTURE;
  }

  function spriteKeyMatches(object, pattern) {
    return [
      object.id,
      object.imageId,
      object.group,
      object.multiobject
    ].some((value) => pattern.test(String(value ?? "")));
  }

  function objectsFor(action, phase) {
    return sprites
      .filter((sprite) => sprite.phase === phase && sprite.group === action.group)
      .sort((left, right) => {
        const diff = naturalIndex(left.id) - naturalIndex(right.id);
        return diff || left.order - right.order;
      });
  }

  function showNextBatch() {
    actionsLayer.replaceChildren();
    state.busy = false;

    const order = orders[state.phase];
    const next = [];

    while (state.cursor < order.length && next.length < BATCH_SIZE) {
      const action = order[state.cursor++];
      if (objectsFor(action, state.phase).length > 0) {
        next.push(action);
      }
    }

    state.batch = next;

    if (next.length === 0) {
      if (state.phase === "repair") {
        state.phase = "decor";
        state.cursor = 0;
        status.textContent = "Decor";
        showNextBatch();
        return;
      }

      status.textContent = "Done";
      triggerDialogs("on_room_finished", {
        triggerKey: currentRoomId,
        roomId: currentRoomId
      });
      return;
    }

    for (const action of next) {
      actionsLayer.appendChild(createActionButton(action));
      triggerDialogs("before_action", {
        triggerKey: action.group,
        objectGroup: action.group,
        phase: state.phase
      });
    }
  }

  function createActionButton(action) {
    const object = objectsFor(action, state.phase)[0];
    const actionPoint = actionPointsByGroup.get(action.group);
    const objectCenter = spriteCenterForObject(object);
    const rawCenterX = actionPoint ? toFiniteNumber(actionPoint.x, objectCenter.x) : objectCenter.x;
    const rawCenterY = actionPoint ? toFiniteNumber(actionPoint.y, objectCenter.y) : objectCenter.y;
    const centerX = clamp(rawCenterX, BUTTON_SIZE / 2, GAME_WIDTH - BUTTON_SIZE / 2);
    const centerY = clamp(rawCenterY, BUTTON_SIZE / 2, GAME_HEIGHT - BUTTON_SIZE / 2);
    const button = document.createElement("button");

    button.className = "action-button";
    button.type = "button";
    button.style.left = `${centerX}px`;
    button.style.top = `${centerY}px`;
    button.setAttribute("aria-label", action.group);

    if (state.phase === "decor") {
      const priceText = decorPriceTextForAction(action, object);
      if (priceText) {
        const price = document.createElement("span");
        price.className = "action-price";
        price.textContent = priceText;
        button.appendChild(price);
        button.setAttribute("aria-label", `${action.group}: ${priceText}`);
      }
    }

    button.addEventListener("click", () => runAction(action, button));

    return button;
  }

  function spriteCenterForObject(object) {
    if (object.coordinates === "center") {
      return { x: object.x, y: object.y };
    }

    const size = spriteRenderSize(object.element, object);
    return {
      x: object.x + size.width / 2,
      y: object.y + size.height / 2
    };
  }

  async function runAction(action, button) {
    if (action.done || state.busy) {
      return;
    }

    state.busy = true;
    button.disabled = true;
    button.style.opacity = "0";

    if (state.phase === "repair") {
      await removeObjects(action);
      finishAction(action, button);
      return;
    }

    const variants = variantsFor(action);
    if (variants.length > 1) {
      await openVariantPicker(action, button, variants);
      return;
    }

    await addObjects(action);
    finishAction(action, button);
  }

  function finishAction(action, button) {
    const completedPhase = state.phase;
    action.done = true;
    button.remove();
    triggerDialogs("after_action", {
      triggerKey: action.group,
      objectGroup: action.group,
      phase: completedPhase
    });

    if (state.batch.every((item) => item.done)) {
      window.setTimeout(showNextBatch, 180);
    } else {
      state.busy = false;
    }
  }

  async function removeObjects(action) {
    const objects = objectsFor(action, "repair").filter((object) => !object.done);

    for (const object of objects) {
      const angle = action.angle ?? angleForObject(object);
      await animateOut(object, angle);
      object.done = true;
      await wait(STEP_DELAY);
    }
  }

  async function addObjects(action) {
    const objects = objectsFor(action, "decor").filter((object) => object.done);

    for (const object of objects) {
      const angle = action.angle ?? angleForObject(object);
      await animateIn(object, angle);
      object.done = false;
      await wait(STEP_DELAY);
    }
  }

  function variantsFor(action) {
    const variants = new Map();

    for (const object of objectsFor(action, "decor")) {
      if (object.variant === null) {
        continue;
      }

      if (!variants.has(object.variant)) {
        variants.set(object.variant, []);
      }

      variants.get(object.variant).push(object);
    }

    return [...variants.entries()]
      .map(([id, objects]) => ({ id, objects }))
      .sort((left, right) => left.id.localeCompare(right.id));
  }

  function normalizePriceValue(value) {
    if (value === null || value === undefined || value === "") {
      return null;
    }

    const price = Number(value);
    return Number.isFinite(price) ? price : null;
  }

  function decorPriceTextForAction(action, object) {
    const variants = variantsFor(action);
    if (variants.length > 1) {
      const prices = variants
        .map((variant) => decorPriceFor(action, variant.id, variant.objects[0]))
        .filter((price) => price !== null);
      return formatPriceRange(prices);
    }

    const price = decorPriceFor(action, object?.variant, object);
    return price === null ? "" : formatPrice(price);
  }

  function decorPriceTextForVariant(action, variant) {
    const price = decorPriceFor(action, variant.id, variant.objects[0]);
    return price === null ? "" : formatPrice(price);
  }

  function decorPriceFor(action, variantId = null, object = null) {
    return normalizePriceValue(object?.price);
  }

  function formatPriceRange(prices) {
    const uniquePrices = [...new Set(prices)].sort((left, right) => left - right);
    if (uniquePrices.length === 0) {
      return "";
    }

    if (uniquePrices.length === 1) {
      return formatPrice(uniquePrices[0]);
    }

    return `${formatPrice(uniquePrices[0])}-${formatPrice(uniquePrices[uniquePrices.length - 1])}`;
  }

  function formatPrice(price) {
    return new Intl.NumberFormat("ru-RU", {
      maximumFractionDigits: 2
    }).format(price);
  }

  async function openVariantPicker(action, button, variants) {
    activeVariant = {
      action,
      button,
      variants,
      selected: null,
      busy: false
    };

    renderVariantOptions();
    variantPanel.classList.remove("hidden");

    const defaultVariant = variants.find((variant) => variant.id === "A") ?? variants[0];
    await selectVariant(defaultVariant.id, true);
  }

  function renderVariantOptions() {
    variantOptions.replaceChildren();

    for (const variant of activeVariant.variants) {
      const option = document.createElement("button");
      const preview = createVariantPreviewElement(variant.objects[0].imageId ?? variant.objects[0].id);

      option.className = "variant-option";
      option.type = "button";
      option.setAttribute("aria-label", `Вариант ${variant.id}`);
      option.dataset.variant = variant.id;
      option.addEventListener("click", () => selectVariant(variant.id, false));

      const priceText = decorPriceTextForVariant(activeVariant.action, variant);
      if (priceText) {
        const price = document.createElement("span");
        price.className = "variant-price";
        price.textContent = priceText;
        option.setAttribute("aria-label", `Р’Р°СЂРёР°РЅС‚ ${variant.id}: ${priceText}`);
        option.append(preview, price);
      } else {
        option.appendChild(preview);
      }

      variantOptions.appendChild(option);
    }
  }

  async function selectVariant(variantId, materialize) {
    if (activeVariant === null || activeVariant.busy || activeVariant.selected === variantId) {
      return;
    }

    activeVariant.busy = true;
    hideVariantObjects(activeVariant.action);

    activeVariant.selected = variantId;
    updateVariantOptionState();

    const selectedObjects = objectsForVariant(variantId);
    for (const object of selectedObjects) {
      object.element.classList.remove("hidden", "animating", "appearing", "removing");
      object.element.style.transform = "translate3d(0, 0, 0) scale(1)";
      object.element.style.opacity = "1";
    }

    if (materialize) {
      await Promise.all(
        selectedObjects.map((object) => animateIn(object, angleForObject(object)))
      );
    } else {
      playVariantSwitch(selectedObjects);
    }

    activeVariant.busy = false;
  }

  function updateVariantOptionState() {
    for (const option of variantOptions.querySelectorAll(".variant-option")) {
      option.classList.toggle("selected", option.dataset.variant === activeVariant.selected);
    }
  }

  function objectsForVariant(variantId) {
    const variant = activeVariant.variants.find((item) => item.id === variantId);
    return variant ? variant.objects : [];
  }

  function hideVariantObjects(action) {
    for (const object of objectsFor(action, "decor")) {
      if (object.variant === null) {
        continue;
      }

      object.element.classList.add("hidden");
      object.element.classList.remove("animating", "appearing", "removing", "variant-switching");
      object.element.style.transform = "translate3d(0, 0, 0) scale(1)";
      object.element.style.opacity = "0";
    }
  }

  function chooseVariant() {
    if (activeVariant === null || activeVariant.busy) {
      return;
    }

    const { action, button, selected } = activeVariant;

    for (const object of objectsFor(action, "decor")) {
      object.done = object.variant !== selected;
      if (object.variant !== selected) {
        object.element.classList.add("hidden");
        object.element.style.opacity = "0";
      }
    }

    hideVariantPanel();
    finishAction(action, button);
  }

  function closeVariantPicker() {
    if (activeVariant === null || activeVariant.busy) {
      return;
    }

    const { action, button } = activeVariant;
    hideVariantObjects(action);
    hideVariantPanel();

    button.disabled = false;
    button.style.opacity = "1";
    state.busy = false;
  }

  function hideVariantPanel() {
    variantPanel.classList.add("hidden");
    variantOptions.replaceChildren();
    activeVariant = null;
  }

  function playVariantSwitch(objects) {
    for (const object of objects) {
      const element = object.element;
      element.classList.remove("variant-switching");
      void element.offsetWidth;
      element.classList.add("variant-switching");
      element.addEventListener("animationend", () => {
        element.classList.remove("variant-switching");
      }, { once: true });
    }
  }

  function triggerDialogs(trigger, context = {}, options = {}) {
    const normalizedTrigger = normalizeDialogTriggerType(trigger);
    const roomIndex = toPositiveInt(context.roomIndex ?? currentRoomIndex, currentRoomIndex);
    const fullContext = {
      ...context,
      roomIndex,
      roomId: String(context.roomId ?? currentRoomId ?? `room${roomIndex}`),
      triggerKey: String(context.triggerKey ?? context.key ?? context.objectGroup ?? "").trim()
    };
    const dialogs = currentRoomId === null ? dialogsConfig.dialogs : activeRoomDialogs;

    for (const dialog of dialogs) {
      if (!dialogMatchesContext(dialog, normalizedTrigger, fullContext)) {
        continue;
      }

      const key = dialogPlayKey(dialog, normalizedTrigger, fullContext);
      if (!options.allowReplay && playedDialogKeys.has(key)) {
        continue;
      }

      if (!options.allowReplay) {
        playedDialogKeys.add(key);
      }

      enqueueDialog(dialog);
    }
  }

  function dialogMatchesContext(dialog, trigger, context) {
    if (dialog.roomIndex !== null && dialog.roomIndex !== context.roomIndex) {
      return false;
    }

    return dialog.conditions.some((condition) => {
      if (condition.trigger !== trigger) {
        return false;
      }

      if (condition.roomIndex !== null && condition.roomIndex !== context.roomIndex) {
        return false;
      }

      if (condition.triggerKey && !triggerKeyMatches(condition.triggerKey, context)) {
        return false;
      }

      if (condition.objectGroup && !triggerKeyMatches(condition.objectGroup, context)) {
        return false;
      }

      if (condition.phase && condition.phase !== context.phase) {
        return false;
      }

      if (condition.levelIndex !== null && condition.levelIndex !== context.levelIndex) {
        return false;
      }

      return true;
    });
  }

  function dialogPlayKey(dialog, trigger, context) {
    const parts = [
      dialog.id,
      trigger,
      context.triggerKey ?? "",
      context.objectGroup ?? "",
      context.phase ?? "",
      context.levelIndex ?? ""
    ];

    return parts.join(":");
  }

  function triggerKeyMatches(expected, context) {
    const expectedKey = String(expected ?? "").trim();
    if (!expectedKey) {
      return true;
    }

    return [
      context.triggerKey,
      context.objectGroup,
      context.roomId
    ].some((candidate) => keysMatch(expectedKey, candidate));
  }

  function keysMatch(left, right) {
    const leftKey = String(left ?? "").trim();
    const rightKey = String(right ?? "").trim();
    if (!leftKey || !rightKey) {
      return false;
    }

    if (leftKey === rightKey) {
      return true;
    }

    return roomlessActionKey(leftKey) === roomlessActionKey(rightKey);
  }

  function roomlessActionKey(value) {
    return String(value)
      .replace(new RegExp(`^${currentRoomId}_`), "")
      .replace(/^room\d+_/, "");
  }

  function enqueueDialog(dialog) {
    const lines = dialog.lines.filter((line) => line.text.trim().length > 0);
    if (lines.length === 0) {
      return;
    }

    dialogQueue.push({
      ...dialog,
      lines
    });

    if (activeDialogPlayback === null) {
      showNextQueuedDialog();
    }
  }

  function showNextQueuedDialog() {
    const nextDialog = dialogQueue.shift();
    if (nextDialog === undefined) {
      closeDialogPlayback();
      return;
    }

    activeDialogPlayback = {
      dialog: nextDialog,
      lineIndex: 0
    };
    renderDialogLine();
  }

  function renderDialogLine() {
    if (activeDialogPlayback === null) {
      return;
    }

    const line = activeDialogPlayback.dialog.lines[activeDialogPlayback.lineIndex];
    const image = normalizeCharacterImagePath(line.image);
    const isRight = line.position === "right";
    const activeCharacter = isRight ? dialogCharacterRight : dialogCharacterLeft;
    const inactiveCharacter = isRight ? dialogCharacterLeft : dialogCharacterRight;

    inactiveCharacter.classList.add("hidden");
    applyCharacterImage(activeCharacter, image, {
      maxWidth: 280,
      maxHeight: 430
    });
    activeCharacter.classList.remove("hidden");
    dialogSpeaker.textContent = characterNameForLine(line);
    dialogText.textContent = line.text;
    dialogOverlay.classList.remove("hidden");
  }

  function advanceDialog() {
    if (activeDialogPlayback === null) {
      return;
    }

    activeDialogPlayback.lineIndex += 1;
    if (activeDialogPlayback.lineIndex >= activeDialogPlayback.dialog.lines.length) {
      showNextQueuedDialog();
      return;
    }

    renderDialogLine();
  }

  function closeDialogPlayback() {
    dialogQueue = [];
    activeDialogPlayback = null;
    dialogOverlay.classList.add("hidden");
    dialogCharacterLeft.classList.add("hidden");
    dialogCharacterRight.classList.add("hidden");
    dialogText.textContent = "";
    dialogSpeaker.textContent = "";
  }

  function changeLevel(delta) {
    if (currentRoomId === null) {
      return;
    }

    levelIndex = Math.max(0, levelIndex + delta);
    updateLevelCounter();
    triggerDialogs("levelCompleted", { levelIndex }, { allowReplay: true });
  }

  function updateLevelCounter() {
    levelValue.textContent = String(levelIndex);
  }

  function handleEditorRoomChange() {
    editorDraft = null;
    editorSelectedId = null;
    renderDialogList();
    renderDialogForm();
  }

  function renderDialogList() {
    const roomIndex = currentEditorRoomIndex();
    const roomDialogs = dialogsConfig.dialogs.filter((dialog) => dialog.roomIndex === roomIndex);
    dialogList.replaceChildren();

    if (roomDialogs.length === 0) {
      const empty = document.createElement("p");
      empty.className = "dialog-list-empty";
      empty.textContent = "Для этого roomindex пока нет диалогов.";
      dialogList.appendChild(empty);
      return;
    }

    for (const dialog of roomDialogs) {
      const item = document.createElement("div");
      const title = document.createElement("div");
      const meta = document.createElement("div");
      const deleteButton = document.createElement("button");

      item.className = "dialog-list-item";
      item.classList.toggle("selected", dialog.id === editorSelectedId);
      item.tabIndex = 0;
      item.addEventListener("click", () => selectDialogForEdit(dialog.id));
      item.addEventListener("keydown", (event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          selectDialogForEdit(dialog.id);
        }
      });

      title.className = "dialog-list-title";
      title.textContent = dialog.id;
      meta.className = "dialog-list-meta";
      meta.textContent = `${dialog.conditions.length} условий, ${dialog.lines.length} реплик`;
      deleteButton.className = "dialog-list-delete row-delete";
      deleteButton.type = "button";
      deleteButton.setAttribute("aria-label", `Удалить ${dialog.id}`);
      deleteButton.textContent = "×";
      deleteButton.addEventListener("click", (event) => {
        event.stopPropagation();
        deleteDialogById(dialog.id);
      });

      item.append(title, meta, deleteButton);
      dialogList.appendChild(item);
    }
  }

  function selectDialogForEdit(dialogId) {
    const dialog = dialogsConfig.dialogs.find((item) => item.id === dialogId);
    if (dialog === undefined) {
      return;
    }

    editorSelectedId = dialog.id;
    editorDraft = cloneDialog(dialog);
    renderDialogList();
    renderDialogForm();
  }

  function createDialogDraft() {
    const roomIndex = currentEditorRoomIndex();
    editorSelectedId = null;
    editorDraft = {
      id: uniqueDialogId(roomIndex),
      roomIndex,
      conditions: [
        { trigger: "on_room_enter", triggerKey: `room${roomIndex}`, roomIndex: null, objectGroup: "", phase: "", levelIndex: null }
      ],
      lines: [
        defaultLine()
      ]
    };

    renderDialogList();
    renderDialogForm();
  }

  function renderDialogForm() {
    if (editorDraft === null) {
      dialogForm.classList.add("hidden");
      return;
    }

    dialogForm.classList.remove("hidden");
    dialogIdInput.value = editorDraft.id;
    dialogRoomIndexInput.value = String(editorDraft.roomIndex);
    renderConditionRows();
    renderLineRows();
  }

  function renderConditionRows() {
    conditionList.replaceChildren();

    for (const [index, condition] of editorDraft.conditions.entries()) {
      const row = document.createElement("div");
      const triggerField = createSelectField("Триггер", TRIGGER_OPTIONS, condition.trigger, "trigger");
      const groupField = createInputField("Trigger key", condition.triggerKey || condition.objectGroup, "triggerKey", "room1_dead_plant");
      const phaseField = createSelectField("Тип", PHASE_OPTIONS, condition.phase, "phase");
      const levelField = createInputField("Level", condition.levelIndex ?? "", "levelIndex", "0", "number");
      const deleteButton = document.createElement("button");

      row.className = "condition-row";
      deleteButton.className = "row-delete";
      deleteButton.type = "button";
      deleteButton.setAttribute("aria-label", "Удалить условие");
      deleteButton.textContent = "×";
      deleteButton.addEventListener("click", () => {
        captureDialogForm();
        editorDraft.conditions.splice(index, 1);
        renderDialogForm();
      });

      row.append(triggerField, groupField, phaseField, levelField, deleteButton);
      conditionList.appendChild(row);
    }
  }

  function renderLineRows() {
    lineList.replaceChildren();

    for (const [index, line] of editorDraft.lines.entries()) {
      const row = document.createElement("div");
      const preview = document.createElement("div");
      const previewImage = document.createElement("div");
      const previewName = document.createElement("div");
      const main = document.createElement("div");
      const imageField = createSelectField("Картинка", characterOptions(), line.image, "image");
      const textField = createTextAreaField("Текст", line.text, "text");
      const positionField = createSelectField("Позиция", POSITION_OPTIONS, line.position, "position");
      const deleteButton = document.createElement("button");
      const imageSelect = imageField.querySelector("select");

      row.className = "line-row";
      preview.className = "line-preview";
      previewImage.className = "character-preview";
      applyCharacterImage(previewImage, line.image, {
        maxWidth: 70,
        maxHeight: 70
      });
      previewName.className = "line-name";
      previewName.textContent = characterNameForImage(line.image);

      imageSelect.addEventListener("change", () => {
        const image = normalizeCharacterImagePath(imageSelect.value);
        applyCharacterImage(previewImage, image, {
          maxWidth: 70,
          maxHeight: 70
        });
        previewName.textContent = characterNameForImage(image);
      });

      main.className = "line-main";
      main.append(imageField, textField);
      deleteButton.className = "row-delete";
      deleteButton.type = "button";
      deleteButton.setAttribute("aria-label", "Удалить реплику");
      deleteButton.textContent = "×";
      deleteButton.addEventListener("click", () => {
        captureDialogForm();
        editorDraft.lines.splice(index, 1);
        renderDialogForm();
      });

      preview.append(previewImage, previewName);
      row.append(preview, main, positionField, deleteButton);
      lineList.appendChild(row);
    }
  }

  function addConditionToDraft() {
    ensureEditorDraft();
    captureDialogForm();
    editorDraft.conditions.push({
      trigger: "on_room_enter",
      triggerKey: `room${currentEditorRoomIndex()}`,
      roomIndex: null,
      objectGroup: "",
      phase: "",
      levelIndex: null
    });
    renderDialogForm();
  }

  function addLineToDraft() {
    ensureEditorDraft();
    captureDialogForm();
    editorDraft.lines.push(defaultLine());
    renderDialogForm();
  }

  function saveDialogDraft(event) {
    if (event !== undefined) {
      event.preventDefault();
    }

    if (editorDraft === null) {
      return;
    }

    const draft = normalizeDialogItem(captureDialogForm(), dialogsConfig.dialogs.length);
    const selectedIndex = dialogsConfig.dialogs.findIndex((dialog) => dialog.id === editorSelectedId);
    const targetIndex = dialogsConfig.dialogs.findIndex((dialog) => dialog.id === draft.id);

    if (targetIndex >= 0) {
      dialogsConfig.dialogs[targetIndex] = draft;
      if (selectedIndex >= 0 && selectedIndex !== targetIndex) {
        dialogsConfig.dialogs.splice(selectedIndex, 1);
      }
    } else if (selectedIndex >= 0) {
      dialogsConfig.dialogs[selectedIndex] = draft;
    } else {
      dialogsConfig.dialogs.push(draft);
    }

    editorSelectedId = draft.id;
    editorDraft = cloneDialog(draft);
    editorRoomIndex.value = String(draft.roomIndex);
    renderDialogList();
    renderDialogForm();
  }

  function deleteSelectedDialog() {
    if (editorSelectedId !== null) {
      deleteDialogById(editorSelectedId);
      return;
    }

    editorDraft = null;
    renderDialogForm();
  }

  function deleteDialogById(dialogId) {
    dialogsConfig.dialogs = dialogsConfig.dialogs.filter((dialog) => dialog.id !== dialogId);
    if (editorSelectedId === dialogId) {
      editorSelectedId = null;
      editorDraft = null;
    }

    renderDialogList();
    renderDialogForm();
  }

  function exportDialogsConfig() {
    if (editorDraft !== null) {
      saveDialogDraft();
    }

    const text = `${JSON.stringify(serializeDialogsConfig(), null, 2)}\n`;
    dialogExportOutput.value = text;
    dialogExportOutput.classList.remove("hidden");

    const blob = new Blob([text], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = "room-dialog-export.json";
    link.click();
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  function ensureEditorDraft() {
    if (editorDraft === null) {
      createDialogDraft();
    }
  }

  function captureDialogForm() {
    if (editorDraft === null) {
      return null;
    }

    editorDraft = {
      id: dialogIdInput.value.trim() || uniqueDialogId(currentEditorRoomIndex()),
      roomIndex: toPositiveInt(dialogRoomIndexInput.value, currentEditorRoomIndex()),
      conditions: [...conditionList.querySelectorAll(".condition-row")].map((row) => ({
        trigger: readRowValue(row, "trigger") || "on_room_enter",
        roomIndex: null,
        triggerKey: readRowValue(row, "triggerKey").trim(),
        objectGroup: readRowValue(row, "triggerKey").trim(),
        phase: readRowValue(row, "phase"),
        levelIndex: toNullableInt(readRowValue(row, "levelIndex"))
      })),
      lines: [...lineList.querySelectorAll(".line-row")].map((row) => ({
        image: normalizeCharacterImagePath(readRowValue(row, "image")),
        text: readRowValue(row, "text"),
        position: readRowValue(row, "position") === "right" ? "right" : "left"
      }))
    };

    return editorDraft;
  }

  function readRowValue(row, field) {
    const element = row.querySelector(`[data-field="${field}"]`);
    return element ? element.value : "";
  }

  function createSelectField(label, options, value, field) {
    const wrapper = document.createElement("label");
    const caption = document.createElement("span");
    const select = document.createElement("select");

    wrapper.className = "editor-field";
    caption.textContent = label;
    select.dataset.field = field;

    for (const option of options) {
      const element = document.createElement("option");
      element.value = option.value;
      element.textContent = option.label;
      select.appendChild(element);
    }

    select.value = value;
    if (select.value !== value && options.length > 0) {
      select.value = options[0].value;
    }

    wrapper.append(caption, select);
    return wrapper;
  }

  function createInputField(label, value, field, placeholder = "", type = "text") {
    const wrapper = document.createElement("label");
    const caption = document.createElement("span");
    const input = document.createElement("input");

    wrapper.className = "editor-field";
    caption.textContent = label;
    input.dataset.field = field;
    input.type = type;
    input.value = value;
    input.placeholder = placeholder;
    wrapper.append(caption, input);
    return wrapper;
  }

  function createTextAreaField(label, value, field) {
    const wrapper = document.createElement("label");
    const caption = document.createElement("span");
    const textarea = document.createElement("textarea");

    wrapper.className = "editor-field";
    caption.textContent = label;
    textarea.dataset.field = field;
    textarea.value = value;
    wrapper.append(caption, textarea);
    return wrapper;
  }

  function serializeDialogsConfig() {
    return {
      characters: dialogsConfig.characters,
      dialogs: dialogsConfig.dialogs.map((dialog) => ({
        id: dialog.id,
        roomIndex: dialog.roomIndex,
        conditions: dialog.conditions.map(serializeCondition),
        replicas: dialog.lines.map((line, index) => {
          const replicaId = line.id || `${dialog.id}_r${index + 1}`;
          const charState = line.charState || characterStateFromImage(line.image);
          return {
            id: replicaId,
            char_key: line.charKey || charKeyForState(charState),
            char_state: charState,
            position: line.position,
            text_key: line.textKey || `${replicaId}_loc`
          };
        })
      }))
    };
  }

  function serializeCondition(condition) {
    const output = {
      trigger_type: condition.trigger
    };

    if (condition.triggerKey || condition.objectGroup) {
      output.trigger_key = condition.triggerKey || condition.objectGroup;
    }

    if (condition.phase) {
      output.phase = condition.phase;
    }

    if (condition.levelIndex !== null) {
      output.levelIndex = condition.levelIndex;
    }

    return output;
  }

  function normalizeDialogsConfig(config, dialogTexts = {}) {
    const characterNames = {
      ...DEFAULT_CHARACTER_NAMES
    };
    const characterKeys = {};
    const characterStateKeys = {};
    const characters = [];

    if (config.characterNames && typeof config.characterNames === "object" && !Array.isArray(config.characterNames)) {
      for (const [image, name] of Object.entries(config.characterNames)) {
        characterNames[normalizeCharacterImagePath(image)] = String(name);
      }
    }

    if (Array.isArray(config.characters)) {
      for (const character of config.characters) {
        if (character === null || typeof character !== "object") {
          continue;
        }

        const id = String(character.id ?? "").trim();
        const key = String(character.name_key ?? character.key ?? character.char_key ?? (id ? `${id}_loc` : "")).trim();
        const name = String(dialogTexts[key] ?? character.name ?? "").trim();
        const states = Array.isArray(character.states)
          ? character.states.map((state) => String(state).trim()).filter(Boolean)
          : [];

        if (key) {
          characterKeys[key] = name || key;
          if (id) {
            characterKeys[`${id}_key`] = name || key;
          }
          characters.push({
            id,
            name_key: String(character.name_key ?? key),
            states
          });
        }

        for (const state of states) {
          if (key) {
            characterStateKeys[state] = key;
          }
          if (name) {
            characterNames[normalizeCharacterStateImage(state)] = name;
          }
        }

        if (character.image && character.name) {
          characterNames[normalizeCharacterImagePath(character.image)] = String(character.name);
        }
      }
    } else if (config.characters && typeof config.characters === "object") {
      for (const [keyOrImage, value] of Object.entries(config.characters)) {
        if (value && typeof value === "object") {
          const id = String(value.id ?? "").trim();
          const key = String(value.name_key ?? value.key ?? keyOrImage ?? (id ? `${id}_loc` : "")).trim();
          const name = String(dialogTexts[key] ?? value.name ?? "").trim();
          const states = Array.isArray(value.states)
            ? value.states.map((state) => String(state).trim()).filter(Boolean)
            : [];

          if (key) {
            characterKeys[key] = name || key;
            if (id) {
              characterKeys[`${id}_key`] = name || key;
            }
            characters.push({
              id,
              name_key: String(value.name_key ?? key),
              states
            });
          }

          for (const state of states) {
            if (key) {
              characterStateKeys[state] = key;
            }
            if (name) {
              characterNames[normalizeCharacterStateImage(state)] = name;
            }
          }
        } else {
          characterNames[normalizeCharacterImagePath(keyOrImage)] = String(value);
        }
      }
    }

    return {
      characters,
      characterStateKeys,
      characterKeys,
      characterNames,
      dialogTexts,
      dialogs: Array.isArray(config.dialogs)
        ? config.dialogs.map((dialog, index) => normalizeDialogItem(dialog, index, {
          characterStateKeys,
          dialogTexts
        })).filter(Boolean)
        : []
    };
  }

  function normalizeDialogItem(dialog, index = 0, context = {}) {
    if (dialog === null || typeof dialog !== "object") {
      return null;
    }

    const roomIndex = toPositiveInt(
      dialog.roomIndex ?? dialog.roomindex ?? context.roomIndex ?? roomIndexFromId(dialog.roomId ?? dialog.room ?? dialog.id),
      1
    );
    const roomId = String(dialog.roomId ?? dialog.room ?? context.roomId ?? `room${roomIndex}`).trim();
    const conditions = Array.isArray(dialog.conditions)
      ? dialog.conditions.map((condition) => normalizeCondition(condition, { roomId, roomIndex })).filter(Boolean)
      : [];
    const rawLines = Array.isArray(dialog.replicas) ? dialog.replicas : dialog.lines;
    const lines = Array.isArray(rawLines)
      ? rawLines.map((line) => normalizeLine(line, context)).filter(Boolean)
      : [];

    return {
      id: String(dialog.id || `dialog_${index + 1}`),
      roomId,
      roomIndex,
      conditions,
      lines
    };
  }

  function normalizeCondition(condition, context = {}) {
    if (condition === null || typeof condition !== "object") {
      return null;
    }

    const trigger = normalizeDialogTriggerType(condition.trigger_type ?? condition.triggerType ?? condition.trigger);
    const triggerKey = normalizeDialogTriggerKey(
      String(condition.trigger_key ?? condition.triggerKey ?? condition.key ?? condition.objectGroup ?? condition.group ?? "").trim(),
      trigger,
      context
    );
    const phase = condition.phase === "repair" || condition.phase === "decor" ? condition.phase : "";

    return {
      trigger,
      triggerKey,
      roomIndex: toNullableInt(condition.roomIndex ?? condition.roomindex),
      objectGroup: trigger === "before_action" || trigger === "after_action" ? triggerKey : "",
      phase,
      levelIndex: toNullableInt(condition.levelIndex ?? condition.level)
    };
  }

  function normalizeDialogTriggerType(value) {
    const key = String(value ?? "").trim();
    if (!key) {
      return "on_room_enter";
    }

    const slug = key.replace(/([a-z])([A-Z])/g, "$1_$2")
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "_")
      .replace(/^_+|_+$/g, "");
    const aliases = {
      room_entered: "on_room_enter",
      room_enter: "on_room_enter",
      on_room_enter: "on_room_enter",
      room_completed: "on_room_finished",
      room_finished: "on_room_finished",
      on_room_finished: "on_room_finished",
      object_bought: "after_action",
      after_action: "after_action",
      before_action: "before_action",
      level_completed: "levelCompleted"
    };

    return aliases[slug] ?? (TRIGGER_OPTIONS.some((option) => option.value === key) ? key : "on_room_enter");
  }

  function normalizeDialogTriggerKey(value, trigger, context = {}) {
    const key = String(value ?? "").trim();
    if (key) {
      return key;
    }

    if (trigger === "on_room_enter" || trigger === "on_room_finished") {
      return String(context.roomId ?? `room${context.roomIndex ?? 1}`);
    }

    return "";
  }

  function normalizeLine(line, context = {}) {
    if (line === null || typeof line !== "object") {
      return null;
    }

    const charState = String(line.char_state ?? line.charState ?? characterStateFromImage(line.image ?? line.characterImage ?? line.avatar ?? firstCharacterImage())).trim();
    const charKey = String(line.char_key ?? line.charKey ?? context.characterStateKeys?.[charState] ?? "").trim();
    const textKey = String(line.text_key ?? line.textKey ?? "").trim();
    const text = String(
      (textKey && context.dialogTexts ? context.dialogTexts[textKey] : undefined)
        ?? line.text
        ?? ""
    );

    return {
      id: String(line.id ?? ""),
      charKey,
      charState,
      textKey,
      image: normalizeCharacterStateImage(charState),
      position: line.position === "right" ? "right" : "left",
      text
    };
  }

  function createDefaultDialogsConfig() {
    return {
      characters: [],
      characterKeys: {},
      characterNames: DEFAULT_CHARACTER_NAMES,
      dialogTexts: {},
      dialogs: []
    };
  }

  function defaultLine() {
    const image = firstCharacterImage();
    const charState = characterStateFromImage(image);
    return {
      id: "",
      charKey: charKeyForState(charState),
      charState,
      textKey: "",
      image,
      text: "",
      position: "left"
    };
  }

  function firstCharacterImage() {
    return Object.keys(dialogsConfig.characterNames ?? DEFAULT_CHARACTER_NAMES)[0]
      ?? Object.keys(DEFAULT_CHARACTER_NAMES)[0];
  }

  function characterOptions() {
    return Object.entries(dialogsConfig.characterNames)
      .map(([image, name]) => ({
        value: normalizeCharacterImagePath(image),
        label: `${name} - ${baseName(image)}`
      }));
  }

  function characterNameForImage(image) {
    const normalized = normalizeCharacterImagePath(image);
    return dialogsConfig.characterNames[normalized]
      ?? dialogsConfig.characterNames[normalizeCharacterStateImage(characterStateFromImage(normalized))]
      ?? dialogsConfig.characterNames[baseName(normalized)]
      ?? "Персонаж";
  }

  function characterNameForLine(line) {
    return dialogsConfig.characterKeys?.[line.charKey]
      ?? characterNameForImage(line.image);
  }

  function charKeyForState(charState) {
    return dialogsConfig.characterStateKeys?.[charState]
      ?? `${String(charState || "unknown").split("_", 1)[0]}_loc`;
  }

  function characterStateFromImage(image) {
    return baseName(image).replace(/\.(?:png|webp|jpe?g)$/i, "");
  }

  function characterIdFromState(charState) {
    return String(charState ?? "").split("_", 1)[0].trim();
  }

  function normalizeCharacterStateImage(charState) {
    const value = String(charState ?? "").trim();
    if (value.length === 0) {
      return normalizeCharacterImagePath(firstCharacterImage());
    }

    if (/^(?:https?:|data:|\/|images\/)/.test(value)) {
      return normalizeCharacterImagePath(value);
    }

    return normalizeCharacterImagePath(value.endsWith(".png") ? value : `${value}.png`);
  }

  function normalizeCharacterImagePath(image) {
    const value = String(image ?? "").trim();
    if (value.length === 0) {
      return Object.keys(DEFAULT_CHARACTER_NAMES)[0];
    }

    if (/^(?:https?:|data:|\/)/.test(value)) {
      return value;
    }

    if (value.startsWith("images/") && !value.startsWith(`${CHARACTER_IMAGE_ROOT}/`)) {
      return value;
    }

    const path = value.startsWith(`${CHARACTER_IMAGE_ROOT}/`)
      ? value
      : `${CHARACTER_IMAGE_ROOT}/${value}`;

    return normalizeCharacterAssetPath(path);
  }

  function normalizeCharacterAssetPath(path) {
    const normalized = String(path).replace(/\\/g, "/");
    const prefix = `${CHARACTER_IMAGE_ROOT}/`;
    if (!normalized.startsWith(prefix)) {
      return normalized;
    }

    const relative = normalized.slice(prefix.length);
    if (!relative || relative.includes("/")) {
      return normalized;
    }

    const fileName = baseName(relative);
    const state = fileName.replace(/\.(?:png|webp|jpe?g)$/i, "");
    const id = characterIdFromState(state);
    return id ? `${prefix}${id}/${fileName}` : normalized;
  }

  function cloneDialog(dialog) {
    return {
      id: dialog.id,
      roomIndex: dialog.roomIndex,
      conditions: dialog.conditions.map((condition) => ({ ...condition })),
      lines: dialog.lines.map((line) => ({ ...line }))
    };
  }

  function uniqueDialogId(roomIndex) {
    let index = 1;
    let id = `room${roomIndex}_dialog_${index}`;
    const ids = new Set(dialogsConfig.dialogs.map((dialog) => dialog.id));

    while (ids.has(id)) {
      index += 1;
      id = `room${roomIndex}_dialog_${index}`;
    }

    return id;
  }

  function currentEditorRoomIndex() {
    return toPositiveInt(editorRoomIndex.value, 1);
  }

  function initialRoomIndex(rooms) {
    const room = rooms[0];
    return room ? toPositiveInt(room.number ?? roomIndexFromId(room.id), 1) : 1;
  }

  function roomIndexFromId(roomId) {
    const match = String(roomId).match(/(\d+)$/);
    return match ? Number(match[1]) : 1;
  }

  function toPositiveInt(value, fallback) {
    const number = Number(value);
    return Number.isFinite(number) && number >= 1 ? Math.floor(number) : fallback;
  }

  function toFiniteNumber(value, fallback) {
    const number = Number(value);
    return Number.isFinite(number) ? number : fallback;
  }

  function toNullableInt(value) {
    if (value === null || value === undefined || value === "") {
      return null;
    }

    const number = Number(value);
    return Number.isFinite(number) ? Math.floor(number) : null;
  }

  function baseName(path) {
    return String(path).split("/").pop() ?? "";
  }

  function atlasSafeName(value) {
    return String(value)
      .replace(/[^A-Za-z0-9_.-]+/g, "_")
      .replace(/_+/g, "_")
      .replace(/^_+|_+$/g, "") || "atlas";
  }

  function createRoomImageElement(imageId) {
    if (atlasFrameFor(imageId) !== null) {
      const element = document.createElement("div");
      applyAtlasFrame(element, imageId);
      return element;
    }

    const element = document.createElement("img");
    element.src = roomImageUrl(imageId);
    element.alt = "";
    return element;
  }

  function createVariantPreviewElement(imageId) {
    const frame = atlasFrameFor(imageId);
    if (frame !== null) {
      const element = document.createElement("div");
      const size = atlasFrameSourceSize(frame);
      const scale = Math.min(84 / size.w, 68 / size.h, 1);
      element.className = "variant-preview";
      applyAtlasFrame(element, imageId, scale);
      return element;
    }

    const element = document.createElement("img");
    element.src = roomImageUrl(imageId);
    element.alt = "";
    return element;
  }

  function applyCharacterImage(element, image, options = {}) {
    const normalized = normalizeCharacterImagePath(image);
    const frameId = characterStateFromImage(normalized);
    const frame = atlasFrameFor(frameId, characterAtlas);

    if (frame !== null) {
      const scale = atlasFrameScale(frame, options);
      if (element instanceof HTMLImageElement) {
        element.src = TRANSPARENT_PIXEL_DATA_URL;
        element.alt = "";
      }
      applyAtlasFrame(element, frameId, scale, characterAtlas);
      return;
    }

    clearImageSurface(element);
    if (element instanceof HTMLImageElement) {
      element.src = normalized;
      element.alt = "";
      return;
    }

    element.style.backgroundImage = `url("${normalized}")`;
    element.style.backgroundPosition = "center";
    element.style.backgroundRepeat = "no-repeat";
    element.style.backgroundSize = "contain";
    if (Number.isFinite(options.maxWidth)) {
      element.style.width = `${options.maxWidth}px`;
    }
    if (Number.isFinite(options.maxHeight)) {
      element.style.height = `${options.maxHeight}px`;
    }
  }

  function atlasFrameScale(frame, options = {}) {
    const size = atlasFrameSourceSize(frame);
    if (size.w <= 0 || size.h <= 0) {
      return 1;
    }

    const maxWidth = toFiniteNumber(options.maxWidth, size.w);
    const maxHeight = toFiniteNumber(options.maxHeight, size.h);
    return Math.min(maxWidth / size.w, maxHeight / size.h, 1);
  }

  function applyRoomImage(element, imageId) {
    if (applyAtlasFrame(element, imageId)) {
      return;
    }

    clearRoomImage(element);
    element.style.backgroundImage = `url("${roomImageUrl(imageId)}")`;
    element.style.backgroundSize = "100% 100%";
  }

  function clearRoomImage(element) {
    clearImageSurface(element);
  }

  function clearImageSurface(element) {
    if (element instanceof HTMLImageElement) {
      element.removeAttribute("src");
    }

    element.style.backgroundImage = "";
    element.style.backgroundPosition = "";
    element.style.backgroundRepeat = "";
    element.style.backgroundSize = "";
    element.style.width = "";
    element.style.height = "";
  }

  function applyAtlasFrame(element, imageId, scale = 1, atlas = currentRoomAtlas) {
    const frame = atlasFrameFor(imageId, atlas);
    if (frame === null || frame.rotated || frame.atlasWidth <= 0 || frame.atlasHeight <= 0) {
      return false;
    }

    const rect = frame.frame;
    const sourceSize = atlasFrameSourceSize(frame);
    const spriteSourceSize = frame.spriteSourceSize ?? { x: 0, y: 0 };

    element.style.backgroundImage = `url("${frame.atlasImageUrl}")`;
    element.style.backgroundPosition = `${(toFiniteNumber(spriteSourceSize.x, 0) - rect.x) * scale}px ${(toFiniteNumber(spriteSourceSize.y, 0) - rect.y) * scale}px`;
    element.style.backgroundRepeat = "no-repeat";
    element.style.backgroundSize = `${frame.atlasWidth * scale}px ${frame.atlasHeight * scale}px`;
    element.style.width = `${sourceSize.w * scale}px`;
    element.style.height = `${sourceSize.h * scale}px`;
    return true;
  }

  function atlasFrameFor(imageId, atlas = currentRoomAtlas) {
    const frame = atlas?.frames?.[String(imageId)];
    return frame && typeof frame === "object" && frame.frame ? frame : null;
  }

  function atlasFrameSourceSize(frame) {
    return {
      w: toFiniteNumber(frame.sourceSize?.w, toFiniteNumber(frame.frame?.w, 0)),
      h: toFiniteNumber(frame.sourceSize?.h, toFiniteNumber(frame.frame?.h, 0))
    };
  }

  function roomImageUrl(imageId) {
    return `${ROOM_IMAGE_ROOT}/${currentRoomId}/${imageId}.png`;
  }

  function vectorForAngle(angle) {
    const radians = angle * Math.PI / 180;
    return {
      x: Math.sin(radians),
      y: -Math.cos(radians)
    };
  }

  async function animateOut(object, angle) {
    const element = object.element;
    const stationary = angle === 180;
    const vector = stationary ? { x: 0, y: 0 } : vectorForAngle(angle);
    const dx = Math.round(vector.x * OUT_DISTANCE);
    const dy = Math.round(vector.y * OUT_DISTANCE);

    element.classList.add("animating", "removing");
    element.style.transform = `translate3d(${dx}px, ${dy}px, 0) scale(.96)`;
    element.style.opacity = "0";

    await waitForTransition(element);
    element.classList.add("hidden");
    element.classList.remove("animating", "removing");
  }

  async function animateIn(object, angle) {
    const element = object.element;
    const stationary = angle === 180;
    const vector = stationary ? { x: 0, y: 0 } : vectorForAngle(angle);
    const dx = Math.round(vector.x * OUT_DISTANCE);
    const dy = Math.round(vector.y * OUT_DISTANCE);

    element.classList.remove("hidden");
    element.classList.add("animating", "appearing");
    element.style.transform = `translate3d(${dx}px, ${dy}px, 0) scale(.96)`;
    element.style.opacity = "0";

    await nextFrame();
    element.style.transform = "translate3d(0, 0, 0) scale(1)";
    element.style.opacity = "1";

    await waitForTransition(element);
    element.classList.remove("animating", "appearing");
  }

  function waitForTransition(element) {
    return new Promise((resolve) => {
      const fallback = window.setTimeout(resolve, 700);

      element.addEventListener("transitionend", () => {
        window.clearTimeout(fallback);
        resolve();
      }, { once: true });
    });
  }

  function nextFrame() {
    return new Promise((resolve) => {
      window.requestAnimationFrame(() => {
        window.requestAnimationFrame(resolve);
      });
    });
  }

  function wait(delay) {
    return new Promise((resolve) => window.setTimeout(resolve, delay));
  }

  function clamp(value, min, max) {
    return Math.min(Math.max(value, min), max);
  }

  function syncScale() {
    const scale = Math.min(window.innerWidth / GAME_WIDTH, window.innerHeight / GAME_HEIGHT, 1);

    shell.style.width = `${GAME_WIDTH * scale}px`;
    shell.style.height = `${GAME_HEIGHT * scale}px`;
    game.style.transform = `scale(${scale})`;
  }
})();
