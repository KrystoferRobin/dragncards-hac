/** Map a stored plugin game_def into builder form state, and merge edits back. */

const GROUP_TYPE_LABELS = {
  deck: "Deck",
  discard: "Discard",
  hand: "Hand",
  inPlay: "In Play",
  aside: "Aside",
};

const GROUP_TYPE_VALUES = {
  Deck: "deck",
  Discard: "discard",
  Hand: "hand",
  "In Play": "inPlay",
  Aside: "aside",
};

export const builderGroupTypeLabel = (groupType) =>
  GROUP_TYPE_LABELS[groupType] || groupType || "Aside";

export const builderGroupTypeValue = (label) => {
  if (GROUP_TYPE_VALUES[label]) return GROUP_TYPE_VALUES[label];
  return (label || "aside").replace(/\s+/g, "");
};

const parsePercentNumber = (value) => {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  const text = String(value ?? "").trim();
  const match = text.match(/-?[\d.]+/);
  return match ? Number(match[0]) : 0;
};

const propertiesToList = (properties) =>
  Object.entries(properties || {}).map(([propertyId, prop]) => ({
    propertyId,
    label: prop?.label || propertyId,
    type: prop?.type || "string",
    default: prop?.default ?? "",
    showInTopBar: !!prop?.showInTopBar,
  }));

const listToProperties = (list, source) => {
  const properties = {};
  (list || []).forEach((prop) => {
    if (!prop?.propertyId) return;
    const previous = source?.[prop.propertyId] || {};
    properties[prop.propertyId] = {
      ...previous,
      label: prop.label || previous.label || prop.propertyId,
      type: prop.type || previous.type || "string",
      default: prop.default ?? previous.default ?? "",
    };
  });
  return properties;
};

export const gameDefToBuilderInputs = (plugin) => {
  const gameDef = plugin?.game_def || {};
  const cardDb = plugin?.card_db || {};
  const groups = Object.entries(gameDef.groups || {}).map(([groupId, group]) => ({
    groupId,
    label: group?.label || groupId,
    groupType: builderGroupTypeLabel(group?.groupType),
    controller: group?.onCardEnter?.controller || "shared",
    correspondingDeck: group?.onCardEnter?.deckGroupId || "",
  }));

  const layoutIds = Object.keys(gameDef.layouts || {});
  const primaryLayoutId = gameDef.layouts?.default ? "default" : (layoutIds[0] || "default");
  const defaultLayout = gameDef.layouts?.[primaryLayoutId] || {};
  const canvasWidth = 1600;
  const canvasHeight = 900;
  const rectangles = Object.entries(defaultLayout.regions || {}).map(([id, region], index) => ({
    id: Date.now() + index,
    text: region?.groupId || id,
    type: region?.type === "fan" ? "fan" : region?.type || "row",
    direction: region?.direction || (region?.type === "free" ? "free" : "horizontal"),
    x: (parsePercentNumber(region?.left) / 100) * canvasWidth,
    y: (parsePercentNumber(region?.top) / 100) * canvasHeight,
    width: (parsePercentNumber(region?.width) / 100) * canvasWidth,
    height: (parsePercentNumber(region?.height) / 100) * canvasHeight,
  }));

  const cardSize = Number(defaultLayout.cardSize) || 16;
  const numRows = Math.max(1, Math.round(100 / (cardSize + 4)));

  const stepsByPhase = {};
  Object.entries(gameDef.steps || {}).forEach(([stepId, step]) => {
    const phaseId = step?.phaseId;
    if (!phaseId) return;
    if (!stepsByPhase[phaseId]) stepsByPhase[phaseId] = [];
    stepsByPhase[phaseId].push({ stepId, label: step?.label || stepId });
  });
  if (Array.isArray(gameDef.stepOrder)) {
    const order = new Map(gameDef.stepOrder.map((stepId, index) => [stepId, index]));
    Object.values(stepsByPhase).forEach((steps) => {
      steps.sort((a, b) => (order.get(a.stepId) ?? 0) - (order.get(b.stepId) ?? 0));
    });
  }

  const phaseOrder = gameDef.phaseOrder || Object.keys(gameDef.phases || {});
  const phases = phaseOrder.map((phaseId) => ({
    phaseId,
    label: gameDef.phases?.[phaseId]?.label || phaseId,
    steps: stepsByPhase[phaseId] || [],
  }));

  const tokens = Object.entries(gameDef.tokens || {}).map(([id, token]) => ({
    id,
    label: token?.label || id,
    left: parsePercentNumber(token?.left),
    top: parsePercentNumber(token?.top),
    width: parsePercentNumber(token?.width) || 4,
    height: parsePercentNumber(token?.height) || 4,
    imageUrl: token?.imageUrl || "",
  }));

  const playerBar = new Set((gameDef.topBarCounters?.player || []).map((item) => item.playerProperty).filter(Boolean));
  const gameBar = new Set((gameDef.topBarCounters?.shared || []).map((item) => item.gameProperty).filter(Boolean));
  const playerProperties = propertiesToList(gameDef.playerProperties).map((prop) => ({
    ...prop,
    showInTopBar: playerBar.has(prop.propertyId),
  }));
  const gameProperties = propertiesToList(gameDef.gameProperties).map((prop) => ({
    ...prop,
    showInTopBar: gameBar.has(prop.propertyId),
  }));

  const playerCounts = (gameDef.playerCountMenu || []).map((item) => item.numPlayers).filter((n) => Number.isFinite(n));

  return {
    pluginName: gameDef.pluginName || plugin?.name || "",
    author: gameDef.author || "",
    backgroundUrl: gameDef.backgroundUrl || "",
    bannerUrl: gameDef.bannerUrl || "",
    logoUrl: gameDef.logoUrl || "",
    minPlayers: playerCounts.length ? Math.min(...playerCounts) : 2,
    maxPlayers: playerCounts.length ? Math.max(...playerCounts) : 2,
    cardDb,
    cardTypes: gameDef.cardTypes || {},
    cardBacks: gameDef.cardBacks || {},
    groups,
    faceProperties: propertiesToList(gameDef.faceProperties).map((prop) => ({
      propertyId: prop.propertyId,
      label: prop.label,
      type: prop.type,
    })),
    cardProperties: propertiesToList(gameDef.cardProperties),
    playerProperties,
    gameProperties,
    deckbuilder: {
      maxCardQuantity: Math.max(1, ...(gameDef.deckbuilder?.addButtons || [3])),
      searchableColumns: (gameDef.deckbuilder?.columns || []).map((col) => ({
        propertyId: col.propName || col.propertyId,
        label: col.label || col.propName,
      })),
    },
    layout: {
      layoutId: primaryLayoutId,
      rectangles,
      chatBox: defaultLayout.chat || { left: "75%", top: "80%", width: "25%", height: "20%" },
      numRows,
      canvasWidth,
      canvasHeight,
    },
    phases,
    tokens,
    imageUrlPrefix: gameDef.imageUrlPrefix || {},
    sourcePlugin: {
      id: plugin.id,
      version: plugin.version,
      public: plugin.public,
      name: plugin.name || gameDef.pluginName,
      author_id: plugin.author_id,
      repo_url: plugin.repo_url || "",
    },
    sourceGameDef: gameDef,
  };
};

const percent = (pixels, total) => {
  if (!total) return "0%";
  return `${((Number(pixels) / total) * 100).toFixed(1)}%`;
};

const applyLayout = (sourceLayouts, layout) => {
  if (!layout) return sourceLayouts || {};
  const layoutId = layout.layoutId || (sourceLayouts?.default ? "default" : Object.keys(sourceLayouts || {})[0]) || "default";
  const sourceDefault = sourceLayouts?.[layoutId] || {};
  const width = layout.canvasWidth || 1600;
  const height = layout.canvasHeight || 900;
  const regions = {};
  (layout.rectangles || []).forEach((rect) => {
    const groupId = rect.text;
    if (!groupId) return;
    const previous = sourceDefault.regions?.[groupId] || {};
    regions[groupId] = {
      ...previous,
      groupId,
      type: rect.type || previous.type || "row",
      direction: rect.direction || (rect.type === "free" ? "free" : previous.direction || "horizontal"),
      left: percent(rect.x, width),
      top: percent(rect.y, height),
      width: percent(rect.width, width),
      height: percent(rect.height, height),
    };
    if (rect.type === "fan" || rect.type === "hand") {
      regions[groupId].disableDroppableAttachments = true;
    }
  });

  return {
    ...sourceLayouts,
    [layoutId]: {
      ...sourceDefault,
      cardSize: Math.ceil((1 / (layout.numRows || 5)) * 100 - 4),
      rowSpacing: sourceDefault.rowSpacing ?? 3,
      chat: layout.chatBox || sourceDefault.chat,
      regions,
      tableButtons: sourceDefault.tableButtons,
      textBoxes: sourceDefault.textBoxes,
    },
  };
};

const applyPhases = (inputs, source) => {
  const phases = {};
  const phaseOrder = [];
  const steps = {};
  const stepOrder = [];
  (inputs.phases || []).forEach((phase) => {
    if (!phase.phaseId) return;
    const phaseSteps = phase.steps || [];
    const previousPhase = source?.phases?.[phase.phaseId] || {};
    phases[phase.phaseId] = {
      ...previousPhase,
      label: phase.label || previousPhase.label || phase.phaseId,
      height: previousPhase.height || `${Math.max(7, Math.round(100 / Math.max(1, (inputs.phases || []).length)))}%`,
    };
    phaseOrder.push(phase.phaseId);
    phaseSteps.forEach((step) => {
      if (!step.stepId) return;
      const previousStep = source?.steps?.[step.stepId] || {};
      steps[step.stepId] = {
        ...previousStep,
        phaseId: phase.phaseId,
        label: step.label || previousStep.label || step.stepId,
      };
      stepOrder.push(step.stepId);
    });
  });
  return { phases, phaseOrder, steps, stepOrder };
};

const applyGroups = (sourceGroups, builderGroups) => {
  const next = {};
  (builderGroups || []).forEach((group) => {
    if (!group.groupId) return;
    const previous = sourceGroups?.[group.groupId] || {};
    next[group.groupId] = {
      ...previous,
      groupType: builderGroupTypeValue(group.groupType),
      label: group.label || group.groupId,
      tableLabel: previous.tableLabel || group.label || group.groupId,
      onCardEnter: {
        ...(previous.onCardEnter || {}),
        controller: group.controller || previous.onCardEnter?.controller || "shared",
      },
    };
    if (group.correspondingDeck) {
      next[group.groupId].onCardEnter.deckGroupId = group.correspondingDeck;
    }
  });
  return next;
};

const applyTokens = (sourceTokens, builderTokens) => {
  const next = {};
  (builderTokens || []).forEach((token) => {
    if (!token.id) return;
    const previous = sourceTokens?.[token.id] || {};
    next[token.id] = {
      ...previous,
      label: token.label || token.id,
      left: `${token.left}%`,
      top: `${token.top}%`,
      width: `${token.width}vh`,
      height: `${token.height}vh`,
      imageUrl: token.imageUrl || previous.imageUrl || "",
      canBeNegative: previous.canBeNegative !== false,
    };
  });
  return next;
};

const applyPlayerCountMenu = (sourceMenu, minPlayers, maxPlayers) => {
  const min = Number(minPlayers) || 2;
  const max = Number(maxPlayers) || min;
  const layoutId = sourceMenu?.[0]?.layoutId || "default";
  const options = [];
  for (let i = min; i <= max; i += 1) {
    const previous = (sourceMenu || []).find((item) => item.numPlayers === i);
    options.push(previous || { label: `${i}`, numPlayers: i, layoutId });
  }
  return options;
};

const applyTopBar = (source, playerProperties, gameProperties) => {
  const managedGame = new Set((gameProperties || []).map((prop) => prop.propertyId).filter(Boolean));
  const managedPlayer = new Set((playerProperties || []).map((prop) => prop.propertyId).filter(Boolean));
  const shared = (source?.shared || []).filter((item) => !managedGame.has(item.gameProperty));
  (gameProperties || []).forEach((prop) => {
    if (!prop.showInTopBar || !prop.propertyId) return;
    const previous = (source?.shared || []).find((item) => item.gameProperty === prop.propertyId);
    shared.push(previous || { label: prop.label || prop.propertyId, imageUrl: "", gameProperty: prop.propertyId });
  });
  const player = (source?.player || []).filter((item) => !managedPlayer.has(item.playerProperty));
  (playerProperties || []).forEach((prop) => {
    if (!prop.showInTopBar || !prop.propertyId) return;
    const previous = (source?.player || []).find((item) => item.playerProperty === prop.propertyId);
    player.push(previous || { label: prop.label || prop.propertyId, imageUrl: "", playerProperty: prop.propertyId });
  });
  return { shared, player };
};

export const applyBuilderInputsToGameDef = (sourceGameDef, inputs) => {
  const source = sourceGameDef || {};
  const phasePayload = applyPhases(inputs, source);
  const cardTypes = { ...(source.cardTypes || {}) };
  Object.entries(inputs.cardTypes || {}).forEach(([type, props]) => {
    cardTypes[type] = {
      ...(cardTypes[type] || {}),
      width: props.width ?? cardTypes[type]?.width ?? 0.72,
      height: props.height ?? cardTypes[type]?.height ?? 1.0,
    };
  });
  const cardBacks = { ...(source.cardBacks || {}) };
  Object.entries(inputs.cardBacks || {}).forEach(([type, props]) => {
    cardBacks[type] = {
      ...(cardBacks[type] || {}),
      ...props,
    };
  });

  const deckbuilder = {
    ...(source.deckbuilder || {}),
    addButtons: Array.from({ length: inputs.deckbuilder?.maxCardQuantity || 3 }, (_, i) => i + 1),
    columns: (inputs.deckbuilder?.searchableColumns || []).map((col) => ({
      propName: col.propertyId,
      label: col.label || col.propertyId,
    })),
  };

  return {
    ...source,
    pluginName: inputs.pluginName || source.pluginName,
    author: inputs.author ?? source.author ?? "",
    backgroundUrl: inputs.backgroundUrl ?? source.backgroundUrl ?? "",
    bannerUrl: inputs.bannerUrl ?? source.bannerUrl ?? "",
    logoUrl: inputs.logoUrl ?? source.logoUrl ?? "",
    cardTypes,
    cardBacks,
    groups: applyGroups(source.groups, inputs.groups),
    faceProperties: listToProperties(inputs.faceProperties, source.faceProperties),
    cardProperties: listToProperties(inputs.cardProperties, source.cardProperties),
    playerProperties: listToProperties(inputs.playerProperties, source.playerProperties),
    gameProperties: listToProperties(inputs.gameProperties, source.gameProperties),
    deckbuilder,
    layouts: applyLayout(source.layouts, inputs.layout),
    tokens: applyTokens(source.tokens, inputs.tokens),
    playerCountMenu: applyPlayerCountMenu(source.playerCountMenu, inputs.minPlayers, inputs.maxPlayers),
    topBarCounters: applyTopBar(source.topBarCounters, inputs.playerProperties, inputs.gameProperties),
    ...phasePayload,
  };
};
