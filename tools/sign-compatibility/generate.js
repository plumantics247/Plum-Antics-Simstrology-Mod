const fs = require("fs");
const path = require("path");

const ROOT = path.resolve(__dirname, "..", "..");
const CONFIG = JSON.parse(fs.readFileSync(path.join(__dirname, "config.json"), "utf8"));
const SIGNS = [
  "Aries",
  "Taurus",
  "Gemini",
  "Cancer",
  "Leo",
  "Virgo",
  "Libra",
  "Scorpio",
  "Sagittarius",
  "Capricorn",
  "Aquarius",
  "Pisces",
];
const ELEMENT_BY_SIGN = new Map([
  ["Aries", "Fire"],
  ["Leo", "Fire"],
  ["Sagittarius", "Fire"],
  ["Taurus", "Earth"],
  ["Virgo", "Earth"],
  ["Capricorn", "Earth"],
  ["Gemini", "Air"],
  ["Libra", "Air"],
  ["Aquarius", "Air"],
  ["Cancer", "Water"],
  ["Scorpio", "Water"],
  ["Pisces", "Water"],
]);
const CHANNELS_BY_SLUG = new Map(CONFIG.channels.map((channel) => [channel.slug, channel]));
const VISIBLE_OUTCOME_ORDER = ["compatible", "neutral", "incompatible"];
const LOOT_OUTCOME_ORDER = ["compatible", "incompatible", "neutral"];
const LOOT_OFFSET_BY_OUTCOME = {
  compatible: 1,
  incompatible: 2,
  neutral: 3,
};
const LANE_BUCKETS = {
  Sun: {
    positive: [
      { id: "5266598269715303467", name: "PlumAntics_Big3Mod_Interactions_SmallTalk" },
      { id: "10127643049430895072", name: "PlumAntics_Big3Mod_Interactions_Jokes" },
      { id: "12001818155183118183", name: "PlumAntics_Big3Mod_Interactions_Stories" },
      { id: "6339212856299285564", name: "PlumAntics_Big3Mod_Interactions_Hobbies" },
      { id: "14764055325143177165", name: "PlumAntics_Big3Mod_Interactions_Interests" },
      { id: "12817375570678276355", name: "PlumAntics_Big3Mod_Interactions_Gossip" },
    ],
    negative: [
      { id: "2680312040151898153", name: "PlumAntics_Big3Mod_Interactions_Deception" },
      { id: "13494195548640628702", name: "PlumAntics_Big3Mod_Interactions_Malicious" },
    ],
  },
  Rising: {
    positive: [
      { id: "1751388732367235507", name: "PlumAntics_Big3Mod_Interactions_Compliments" },
      { id: "5266598269715303467", name: "PlumAntics_Big3Mod_Interactions_SmallTalk" },
    ],
    negative: [
      { id: "9966041009495338782", name: "PlumAntics_Big3Mod_Interactions_Complaints" },
      { id: "14029388175093318457", name: "PlumAntics_Big3Mod_Interactions_Pranks" },
    ],
  },
  Moon: {
    positive: [
      { id: "4387253343428166832", name: "PlumAntics_Big3Mod_Interactions_Flirtation" },
      { id: "14502799288215702933", name: "PlumAntics_Big3Mod_Interactions_PhysicalIntimacy" },
      { id: "9474395650096351456", name: "PlumAntics_Big3Mod_Interactions_DeepThoughts" },
    ],
    negative: [
      { id: "556712450165985048", name: "PlumAntics_Big3Mod_Interactions_Arguments" },
    ],
  },
};

function read(relativePath) {
  return fs.readFileSync(path.join(ROOT, relativePath), "utf8");
}

function write(relativePath, text) {
  const target = path.join(ROOT, relativePath);
  fs.mkdirSync(path.dirname(target), { recursive: true });
  fs.writeFileSync(target, text);
}

function render(templateName, replacements) {
  let out = read(path.join(CONFIG.templateFolder, templateName));
  for (const [key, value] of Object.entries(replacements)) {
    out = out.split(`__${key}__`).join(String(value));
  }
  return out;
}

function toSimDataKey(resourceKey) {
  const [type, group, instance] = resourceKey.split(":");
  return `${type.toUpperCase()}-${group.toUpperCase()}-${instance.toUpperCase()}`;
}

function toHexKey(value) {
  return `0x${value.toString(16).toUpperCase().padStart(8, "0")}`;
}

function toOutcomeTitle(outcomeKey) {
  return outcomeKey.charAt(0).toUpperCase() + outcomeKey.slice(1);
}

function cleanGeneratedXmlFolder(relativePath) {
  const target = path.join(ROOT, relativePath);
  if (!fs.existsSync(target)) {
    return;
  }

  for (const entry of fs.readdirSync(target)) {
    if (entry.endsWith(".xml") || entry.endsWith(".SimData.xml")) {
      fs.unlinkSync(path.join(target, entry));
    }
  }
}

function parseTrait(channel, sign) {
  const relativePath = path.join(CONFIG.coreTraitFolder, `PlumAntics_Big3ModCore_${sign}${channel.slug}.xml`);
  const text = read(relativePath);
  const instanceMatch = text.match(/\bs="(\d+)"/);
  const iconMatch = text.match(/<T n="icon">([^<]+)<\/T>/);
  const nameMatch = text.match(/<I[^>]+\bn="([^"]+)"/);
  if (!instanceMatch || !iconMatch || !nameMatch) {
    throw new Error(`Failed to parse trait metadata from ${relativePath}`);
  }
  return {
    sign,
    traitId: instanceMatch[1],
    traitName: nameMatch[1],
    iconKey: iconMatch[1],
  };
}

function buildWeightedTraitMap(channel, targetSign) {
  const targetElement = ELEMENT_BY_SIGN.get(targetSign);
  if (!targetElement) {
    throw new Error(`Missing element mapping for ${targetSign}`);
  }

  return SIGNS.flatMap((sourceSign) => {
    const sourceElement = ELEMENT_BY_SIGN.get(sourceSign);
    if (sourceElement !== targetElement) {
      return [];
    }

    const sourceTrait = parseTrait(channel, sourceSign);
    return [{ traitId: sourceTrait.traitId, traitName: sourceTrait.traitName, weight: 5 }];
  });
}

function getPreferenceTraitMeta(channel, sign, index, polarity) {
  const base = polarity === "like" ? channel.likeTraitBase : channel.dislikeTraitBase;
  const suffix = polarity === "like" ? "Like" : "Dislike";
  return {
    traitId: (BigInt(base) + BigInt(index + 1)).toString(),
    traitName: `PlumAntics_${channel.slug}Compatibility_${sign}${suffix}PreferenceTrait`,
  };
}

function reactionBuffLabel(channelSlug, outcomeKey) {
  const labels = {
    Sun: {
      compatible: "Sun Compatibility Spark",
      neutral: "Sun Compatibility Steady",
      incompatible: "Sun Compatibility Friction",
    },
    Moon: {
      compatible: "Moon Compatibility Ease",
      neutral: "Moon Compatibility Calm",
      incompatible: "Moon Compatibility Static",
    },
    Rising: {
      compatible: "Rising Compatibility Click",
      neutral: "Rising Compatibility Poise",
      incompatible: "Rising Compatibility Tension",
    },
  };
  return labels[channelSlug][outcomeKey];
}

function reactionBuffCopy(channelSlug, outcomeKey) {
  const copy = {
    Sun: {
      compatible: "This Sim feels naturally aligned with a favored Sun sign.",
      neutral: "This Sim feels socially neutral toward this Sun sign for now.",
      incompatible: "This Sim feels immediate value friction with a disliked Sun sign.",
    },
    Moon: {
      compatible: "This Sim feels emotionally at ease with a favored Moon sign.",
      neutral: "This Sim feels emotionally neutral toward this Moon sign for now.",
      incompatible: "This Sim feels emotional tension around a disliked Moon sign.",
    },
    Rising: {
      compatible: "This Sim has a quick positive read on a favored Rising sign.",
      neutral: "This Sim feels socially neutral toward this Rising sign for now.",
      incompatible: "This Sim immediately reads this Rising sign as abrasive or off-putting.",
    },
  };
  return copy[channelSlug][outcomeKey];
}

function ensureStringEntry(entriesByKey, orderedEntries, key, value) {
  const existing = entriesByKey.get(key);
  if (existing) {
    existing.value = value;
    return;
  }

  const created = { key, value };
  entriesByKey.set(key, created);
  orderedEntries.push(created);
}

function upsertStrings() {
  const stringTablePath = path.join(ROOT, CONFIG.stringTablePath);
  const payload = JSON.parse(fs.readFileSync(stringTablePath, "utf8"));
  const orderedEntries = [...payload.entries];
  const entriesByKey = new Map(orderedEntries.map((entry) => [entry.key, entry]));

  for (const channel of CONFIG.channels) {
    ensureStringEntry(entriesByKey, orderedEntries, channel.categoryDisplayNameKey, `${channel.slug} Compatibility`);
    ensureStringEntry(
      entriesByKey,
      orderedEntries,
      channel.categoryDescriptionKey,
      `${channel.slug} Sign`
    );
    ensureStringEntry(
      entriesByKey,
      orderedEntries,
      channel.categoryTooltipKey,
      `${channel.slug} Sign`
    );

    ensureStringEntry(entriesByKey, orderedEntries, channel.buffs.like.nameKey, `${channel.slug} Sign Like`);
    ensureStringEntry(
      entriesByKey,
      orderedEntries,
      channel.buffs.like.descriptionKey,
      channel.slug === "Moon"
        ? "This Sim feels emotionally at ease with favored Moon signs."
        : channel.slug === "Rising"
          ? "This Sim has an easy first impression of favored Rising signs."
          : "This Sim reacts warmly to favored Sun signs."
    );
    ensureStringEntry(entriesByKey, orderedEntries, channel.buffs.dislike.nameKey, `${channel.slug} Sign Dislike`);
    ensureStringEntry(
      entriesByKey,
      orderedEntries,
      channel.buffs.dislike.descriptionKey,
      channel.slug === "Moon"
        ? "This Sim feels emotionally off-balance around disliked Moon signs."
        : channel.slug === "Rising"
          ? "This Sim has a rough first impression of disliked Rising signs."
          : "This Sim reacts poorly to disliked Sun signs."
    );

    const base = Number.parseInt(channel.preferenceStringBase, 16);
    for (const [index, sign] of SIGNS.entries()) {
      const offset = index * 4;
      const likeNameKey = toHexKey(base + offset);
      const likeDescriptionKey = toHexKey(base + offset + 1);
      const dislikeNameKey = toHexKey(base + offset + 2);
      const dislikeDescriptionKey = toHexKey(base + offset + 3);
      ensureStringEntry(entriesByKey, orderedEntries, likeNameKey, `Likes ${sign} ${channel.slug}`);
      ensureStringEntry(
        entriesByKey,
        orderedEntries,
        likeDescriptionKey,
        `This Sim tends to like Sims with ${sign} ${channel.slug}.`
      );
      ensureStringEntry(entriesByKey, orderedEntries, dislikeNameKey, `Dislikes ${sign} ${channel.slug}`);
      ensureStringEntry(
        entriesByKey,
        orderedEntries,
        dislikeDescriptionKey,
        `This Sim tends to dislike Sims with ${sign} ${channel.slug}.`
      );
    }
  }

  if (CONFIG.reaction) {
    for (const reactionChannel of CONFIG.reaction.channels) {
      for (const outcomeKey of VISIBLE_OUTCOME_ORDER) {
        const buff = reactionChannel.visibleBuffs[outcomeKey];
        ensureStringEntry(entriesByKey, orderedEntries, buff.nameKey, reactionBuffLabel(reactionChannel.slug, outcomeKey));
        ensureStringEntry(
          entriesByKey,
          orderedEntries,
          buff.descriptionKey,
          reactionBuffCopy(reactionChannel.slug, outcomeKey)
        );
      }
    }
  }

  payload.entries = orderedEntries;
  fs.writeFileSync(stringTablePath, `${JSON.stringify(payload, null, 4)}\n`);
}

function writeCategory(channel) {
  const replacements = {
    NAME: channel.categoryName,
    INSTANCE: channel.categoryInstance,
    DISPLAY_NAME_KEY: channel.categoryDisplayNameKey,
    DESCRIPTION_KEY: channel.categoryDescriptionKey,
    TOOLTIP_KEY: channel.categoryTooltipKey,
    ICON_KEY: channel.categoryIconKey,
    SIMDATA_ICON_KEY: toSimDataKey(channel.categoryIconKey),
  };

  write(
    path.join(CONFIG.categoryFolder, `${channel.categoryName}.xml`),
    render("category.xml.tmpl", replacements)
  );
  write(
    path.join(CONFIG.categoryFolder, `${channel.categoryName}.SimData.xml`),
    render("category.SimData.xml.tmpl", replacements)
  );
}

function writeBuffs(channel) {
  for (const polarity of ["like", "dislike"]) {
    const buff = channel.buffs[polarity];
    const replacements = {
      NAME: buff.name,
      INSTANCE: buff.instance,
      DISPLAY_NAME_KEY: buff.nameKey,
      DESCRIPTION_KEY: buff.descriptionKey,
      ICON_KEY: channel.categoryIconKey,
      SIMDATA_ICON_KEY: toSimDataKey(channel.categoryIconKey),
      STATISTIC_ID: channel.statistic.instance,
    };

    write(path.join(CONFIG.buffFolder, `${buff.name}.xml`), render("channel_buff.xml.tmpl", replacements));
    write(
      path.join(CONFIG.buffFolder, `${buff.name}.SimData.xml`),
      render("channel_buff.SimData.xml.tmpl", replacements)
    );
  }
}

function writeStatistic(channel) {
  const replacements = {
    NAME: channel.statistic.name,
    INSTANCE: channel.statistic.instance,
  };

  write(
    path.join(CONFIG.statisticFolder, `${channel.statistic.name}.xml`),
    render("channel_statistic.xml.tmpl", replacements)
  );
  write(
    path.join(CONFIG.statisticFolder, `${channel.statistic.name}.SimData.xml`),
    render("channel_statistic.SimData.xml.tmpl", replacements)
  );
}

function writePreferenceItem(channel, sign, index, likeTraitId, dislikeTraitId) {
  const itemInstance = (BigInt(channel.itemBase) + BigInt(index + 1)).toString();
  const name = `PlumAntics_${channel.slug}Compatibility_${sign}Preference`;
  const traitMapLines = buildWeightedTraitMap(channel, sign)
    .map(
      ({ traitId, traitName, weight }) => `    <U>
      <T n="key">${traitId}<!--${traitName}--></T>
      <T n="value">${weight}</T>
    </U>`
    )
    .join("\n");
  const replacements = {
    NAME: name,
    INSTANCE: itemInstance,
    CATEGORY_INSTANCE: channel.categoryInstance,
    LIKE_TRAIT_ID: likeTraitId,
    DISLIKE_TRAIT_ID: dislikeTraitId,
    TRAIT_MAP_LINES: traitMapLines,
  };

  write(
    path.join(CONFIG.preferenceFolder, channel.slug, `${name}.xml`),
    render("preference.xml.tmpl", replacements)
  );
  write(
    path.join(CONFIG.preferenceFolder, channel.slug, `${name}.SimData.xml`),
    render("preference.SimData.xml.tmpl", replacements)
  );

  return { itemInstance, itemName: name };
}

function writePreferenceTraits(channel, traitMeta, index, itemInstance) {
  const likeTraitId = (BigInt(channel.likeTraitBase) + BigInt(index + 1)).toString();
  const dislikeTraitId = (BigInt(channel.dislikeTraitBase) + BigInt(index + 1)).toString();
  const base = Number.parseInt(channel.preferenceStringBase, 16) + index * 4;

  const variants = [
    {
      suffix: "Like",
      instance: likeTraitId,
      traitType: "LIKE",
      traitTypeId: 22,
      displayNameKey: toHexKey(base),
      descriptionKey: toHexKey(base + 1),
      buffId: channel.buffs.like.instance,
      conflictingTraitId: dislikeTraitId,
    },
    {
      suffix: "Dislike",
      instance: dislikeTraitId,
      traitType: "DISLIKE",
      traitTypeId: 23,
      displayNameKey: toHexKey(base + 2),
      descriptionKey: toHexKey(base + 3),
      buffId: channel.buffs.dislike.instance,
      conflictingTraitId: likeTraitId,
    },
  ];

  for (const variant of variants) {
    const name = `PlumAntics_${channel.slug}Compatibility_${traitMeta.sign}${variant.suffix}PreferenceTrait`;
    const replacements = {
      NAME: name,
      INSTANCE: variant.instance,
      PREFERENCE_ITEM_ID: itemInstance,
      ICON_KEY: traitMeta.iconKey,
      SIMDATA_ICON_KEY: toSimDataKey(traitMeta.iconKey),
      DISPLAY_NAME_KEY: variant.displayNameKey,
      DESCRIPTION_KEY: variant.descriptionKey,
      TRAIT_TYPE: variant.traitType,
      TRAIT_TYPE_ID: variant.traitTypeId,
      BUFF_ID: variant.buffId,
      CONFLICTING_TRAIT_ID: variant.conflictingTraitId,
    };

    write(path.join(CONFIG.traitFolder, `${name}.xml`), render("hidden_trait.xml.tmpl", replacements));
    write(
      path.join(CONFIG.traitFolder, `${name}.SimData.xml`),
      render("hidden_trait.SimData.xml.tmpl", replacements)
    );
  }

  return { likeTraitId, dislikeTraitId };
}

function renderAffordanceModifierBlock(listEntries, scoreBonus) {
  const affordanceLines = listEntries
    .map((entry) => `            <T>${entry.id}<!--${entry.name}--></T>`)
    .join("\n");
  return `      <V t="affordance_modifier">
        <U n="affordance_modifier">
          <L n="affordance_lists">
${affordanceLines}
          </L>
          <T n="content_score_bonus">${scoreBonus}</T>
        </U>
      </V>`;
}

function buildTierParameters(channelSlug, outcomeKey) {
  const buckets = LANE_BUCKETS[channelSlug];
  if (outcomeKey === "compatible") {
    const compatibleMultipliers = {
      Sun: { friendship: "1.25", romance: "1.05" },
      Moon: { friendship: "1.05", romance: "1.25" },
      Rising: { friendship: "1.15", romance: "1.05" },
    };
    return {
      friendshipMultiplier: compatibleMultipliers[channelSlug].friendship,
      romanceMultiplier: compatibleMultipliers[channelSlug].romance,
      affordanceModifierBlocks: [
        renderAffordanceModifierBlock(buckets.positive, 10),
        renderAffordanceModifierBlock(buckets.negative, -5),
      ].join("\n"),
    };
  }

  if (outcomeKey === "incompatible") {
    const incompatibleMultipliers = {
      Sun: { friendship: "0.90", romance: "0.95" },
      Moon: { friendship: "0.95", romance: "0.85" },
      Rising: { friendship: "0.90", romance: "0.95" },
    };
    return {
      friendshipMultiplier: incompatibleMultipliers[channelSlug].friendship,
      romanceMultiplier: incompatibleMultipliers[channelSlug].romance,
      affordanceModifierBlocks: [
        renderAffordanceModifierBlock(buckets.positive, -10),
        renderAffordanceModifierBlock(buckets.negative, 5),
      ].join("\n"),
    };
  }

  return {
    friendshipMultiplier: "1",
    romanceMultiplier: "1",
    affordanceModifierBlocks: "",
  };
}

function buildOverlayParameters(channelSlug, outcomeKey) {
  const parameters = {
    Sun: {
      compatible: { friendship: "1.10", romance: "1.00" },
      neutral: { friendship: "1.00", romance: "1.00" },
      incompatible: { friendship: "0.95", romance: "0.95" },
    },
    Moon: {
      compatible: { friendship: "1.00", romance: "1.15" },
      neutral: { friendship: "1.00", romance: "1.00" },
      incompatible: { friendship: "0.95", romance: "0.85" },
    },
    Rising: {
      compatible: { friendship: "1.10", romance: "1.00" },
      neutral: { friendship: "1.00", romance: "1.00" },
      incompatible: { friendship: "0.95", romance: "0.95" },
    },
  };

  return {
    friendshipMultiplier: parameters[channelSlug][outcomeKey].friendship,
    romanceMultiplier: parameters[channelSlug][outcomeKey].romance,
  };
}

function writeOutcomeReactionVisibleBuff(shellChannel, reactionChannel, outcomeKey) {
  const buff = reactionChannel.visibleBuffs[outcomeKey];
  const moodType = outcomeKey === "neutral" ? "14637<!--Mood_Fine-->" : "0";
  const moodWeight = outcomeKey === "neutral" ? "2" : "0";
  const showTimeout = outcomeKey === "neutral" ? "True" : "False";
  const simDataMoodType = outcomeKey === "neutral" ? "14637" : "0";

  const replacements = {
    NAME: buff.name,
    INSTANCE: buff.instance,
    DISPLAY_NAME_KEY: buff.nameKey,
    DESCRIPTION_KEY: buff.descriptionKey,
    ICON_KEY: shellChannel.categoryIconKey,
    SIMDATA_ICON_KEY: toSimDataKey(shellChannel.categoryIconKey),
    MOOD_TYPE: moodType,
    MOOD_WEIGHT: moodWeight,
    SHOW_TIMEOUT: showTimeout,
    SIMDATA_MOOD_TYPE: simDataMoodType,
    SIMDATA_MOOD_WEIGHT: moodWeight,
  };

  write(
    path.join(CONFIG.reaction.visibleBuffFolder, `${buff.name}.xml`),
    render("reaction_visible_buff.xml.tmpl", replacements)
  );
  write(
    path.join(CONFIG.reaction.visibleBuffFolder, `${buff.name}.SimData.xml`),
    render("reaction_visible_buff.SimData.xml.tmpl", replacements)
  );
}

function writeReactionCooldownBuff(reactionChannel) {
  const replacements = {
    NAME: reactionChannel.cooldownBuff.name,
    INSTANCE: reactionChannel.cooldownBuff.instance,
  };

  write(
    path.join(CONFIG.reaction.hiddenBuffFolder, `${reactionChannel.cooldownBuff.name}.xml`),
    render("reaction_cooldown_buff.xml.tmpl", replacements)
  );
  write(
    path.join(CONFIG.reaction.hiddenBuffFolder, `${reactionChannel.cooldownBuff.name}.SimData.xml`),
    render("reaction_cooldown_buff.SimData.xml.tmpl", replacements)
  );
}

function writeLaneTierBuff(reactionChannel, outcomeKey) {
  const buff = reactionChannel.tierBuffs[outcomeKey];
  const parameters = buildTierParameters(reactionChannel.slug, outcomeKey);
  const replacements = {
    NAME: buff.name,
    INSTANCE: buff.instance,
    FRIENDSHIP_MULTIPLIER: parameters.friendshipMultiplier,
    ROMANCE_MULTIPLIER: parameters.romanceMultiplier,
    AFFORDANCE_MODIFIER_BLOCKS: parameters.affordanceModifierBlocks,
  };

  write(
    path.join(CONFIG.reaction.tierBuffFolder, `${buff.name}.xml`),
    render("lane_tier_buff.xml.tmpl", replacements)
  );
  write(
    path.join(CONFIG.reaction.tierBuffFolder, `${buff.name}.SimData.xml`),
    render("lane_tier_buff.SimData.xml.tmpl", replacements)
  );
}

function writeLaneOverlayBuff(reactionChannel, outcomeKey) {
  const buff = reactionChannel.overlayBuffs[outcomeKey];
  const parameters = buildOverlayParameters(reactionChannel.slug, outcomeKey);
  const replacements = {
    NAME: buff.name,
    INSTANCE: buff.instance,
    FRIENDSHIP_MULTIPLIER: parameters.friendshipMultiplier,
    ROMANCE_MULTIPLIER: parameters.romanceMultiplier,
  };

  write(
    path.join(CONFIG.reaction.overlayBuffFolder, `${buff.name}.xml`),
    render("lane_overlay_buff.xml.tmpl", replacements)
  );
  write(
    path.join(CONFIG.reaction.overlayBuffFolder, `${buff.name}.SimData.xml`),
    render("lane_overlay_buff.SimData.xml.tmpl", replacements)
  );
}

function buildPreferenceTestBlock(preferenceTrait, conflictingTrait, outcomeKey) {
  if (outcomeKey === "compatible") {
    return `      <V t="trait">
        <U n="trait">
          <L n="whitelist_traits">
            <T>${preferenceTrait.traitId}<!--${preferenceTrait.traitName}--></T>
          </L>
        </U>
      </V>`;
  }
  if (outcomeKey === "incompatible") {
    return `      <V t="trait">
        <U n="trait">
          <L n="whitelist_traits">
            <T>${conflictingTrait.traitId}<!--${conflictingTrait.traitName}--></T>
          </L>
        </U>
      </V>`;
  }
  return `      <V t="trait">
        <U n="trait">
          <L n="blacklist_traits">
            <T>${preferenceTrait.traitId}<!--${preferenceTrait.traitName}--></T>
            <T>${conflictingTrait.traitId}<!--${conflictingTrait.traitName}--></T>
          </L>
        </U>
      </V>`;
}

function writeOutcomeReactionLoot(shellChannel, reactionChannel, traitMeta, index, outcomeKey) {
  const outcomeTitle = toOutcomeTitle(outcomeKey);
  const likePreferenceTrait = getPreferenceTraitMeta(shellChannel, traitMeta.sign, index, "like");
  const dislikePreferenceTrait = getPreferenceTraitMeta(shellChannel, traitMeta.sign, index, "dislike");
  const visibleBuff = reactionChannel.visibleBuffs[outcomeKey];
  const tierBuff = reactionChannel.tierBuffs[outcomeKey];
  const overlayBuff = reactionChannel.overlayBuffs[outcomeKey];
  const name = `PlumAntics_${shellChannel.slug}Compatibility_${traitMeta.sign}${outcomeTitle}ReactionLoot`;
  const instance = (BigInt(reactionChannel.actionBase) + BigInt(index * 3 + LOOT_OFFSET_BY_OUTCOME[outcomeKey])).toString();
  const replacements = {
    NAME: name,
    INSTANCE: instance,
    TIER_BUFF_ID: tierBuff.instance,
    TIER_BUFF_NAME: tierBuff.name,
    OVERLAY_BUFF_ID: overlayBuff.instance,
    OVERLAY_BUFF_NAME: overlayBuff.name,
    VISIBLE_BUFF_ID: visibleBuff.instance,
    VISIBLE_BUFF_NAME: visibleBuff.name,
    COOLDOWN_BUFF_ID: reactionChannel.cooldownBuff.instance,
    COOLDOWN_BUFF_NAME: reactionChannel.cooldownBuff.name,
    PREFERENCE_TEST_BLOCK: buildPreferenceTestBlock(likePreferenceTrait, dislikePreferenceTrait, outcomeKey),
    TARGET_CORE_TRAIT_ID: traitMeta.traitId,
    TARGET_CORE_TRAIT_NAME: traitMeta.traitName,
  };

  write(path.join(CONFIG.reaction.actionFolder, `${name}.xml`), render("reaction_loot.xml.tmpl", replacements));
  return { instance, name };
}

function writeReactionMixer(reactionChannel, lootEntries) {
  const lootLines = lootEntries
    .map((entry) => `<T>${entry.instance}<!--${entry.name}--></T>`)
    .join("\n          ");
  const replacements = {
    NAME: reactionChannel.mixer.name,
    INSTANCE: reactionChannel.mixer.instance,
    LOOT_LINES: lootLines,
  };

  write(
    path.join(CONFIG.reaction.interactionFolder, `${reactionChannel.mixer.name}.xml`),
    render("reaction_mixer.xml.tmpl", replacements)
  );
}

function writeReactionInjector() {
  const mixerIds = CONFIG.reaction.channels
    .map((reactionChannel) => {
      const mixer = reactionChannel.mixer;
      return `<T>${mixer.instance}<!--${mixer.name}--></T>`;
    })
    .join("\n        ");

  const mixerListBlocks = CONFIG.reaction.friendlyMixerLists
    .map(
      (mixerList) => `    <U>
      <T n="mixer_list">${mixerList.id}<!--${mixerList.comment}--></T>
      <L n="mixers">
        ${mixerIds}
      </L>
    </U>`
    )
    .join("\n");

  const replacements = {
    NAME: CONFIG.reaction.injector.name,
    INSTANCE: CONFIG.reaction.injector.instance,
    MIXER_LIST_BLOCKS: mixerListBlocks,
  };

  write(
    path.join(CONFIG.reaction.injectorFolder, `${CONFIG.reaction.injector.name}.xml`),
    render("reaction_injector.xml.tmpl", replacements)
  );
}

function main() {
  upsertStrings();

  for (const channel of CONFIG.channels) {
    writeCategory(channel);
    writeBuffs(channel);
    writeStatistic(channel);

    for (const [index, sign] of SIGNS.entries()) {
      const traitMeta = parseTrait(channel, sign);
      const likeTraitId = (BigInt(channel.likeTraitBase) + BigInt(index + 1)).toString();
      const dislikeTraitId = (BigInt(channel.dislikeTraitBase) + BigInt(index + 1)).toString();
      const { itemInstance } = writePreferenceItem(channel, sign, index, likeTraitId, dislikeTraitId);
      writePreferenceTraits(channel, traitMeta, index, itemInstance);
    }
  }

  if (CONFIG.reaction) {
    cleanGeneratedXmlFolder(CONFIG.reaction.actionFolder);
    cleanGeneratedXmlFolder(CONFIG.reaction.visibleBuffFolder);
    cleanGeneratedXmlFolder(CONFIG.reaction.hiddenBuffFolder);
    cleanGeneratedXmlFolder(CONFIG.reaction.tierBuffFolder);
    cleanGeneratedXmlFolder(CONFIG.reaction.overlayBuffFolder);
    cleanGeneratedXmlFolder(CONFIG.reaction.interactionFolder);
    cleanGeneratedXmlFolder(CONFIG.reaction.injectorFolder);

    for (const reactionChannel of CONFIG.reaction.channels) {
      const shellChannel = CHANNELS_BY_SLUG.get(reactionChannel.slug);
      if (!shellChannel) {
        throw new Error(`Missing shell channel for reaction channel ${reactionChannel.slug}`);
      }

      for (const outcomeKey of VISIBLE_OUTCOME_ORDER) {
        writeOutcomeReactionVisibleBuff(shellChannel, reactionChannel, outcomeKey);
        writeLaneTierBuff(reactionChannel, outcomeKey);
        writeLaneOverlayBuff(reactionChannel, outcomeKey);
      }
      writeReactionCooldownBuff(reactionChannel);

      const lootEntries = [];
      for (const [index, sign] of SIGNS.entries()) {
        const traitMeta = parseTrait(shellChannel, sign);
        for (const outcomeKey of LOOT_OUTCOME_ORDER) {
          lootEntries.push(writeOutcomeReactionLoot(shellChannel, reactionChannel, traitMeta, index, outcomeKey));
        }
      }

      writeReactionMixer(reactionChannel, lootEntries);
    }

    writeReactionInjector();
  }
}

main();
