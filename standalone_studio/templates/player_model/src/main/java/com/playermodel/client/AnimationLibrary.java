package com.playermodel.client;

import com.google.gson.JsonArray;
import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import com.google.gson.JsonParser;
import net.minecraft.client.Minecraft;
import net.minecraft.client.renderer.entity.state.AvatarRenderState;
import net.minecraft.resources.Identifier;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.io.BufferedReader;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.util.LinkedHashMap;
import java.util.Map;

public final class AnimationLibrary {
    private static final Logger LOGGER = LoggerFactory.getLogger("player_model");
    private final Map<String, RunClip> clips;

    private AnimationLibrary(Map<String, RunClip> clips) {
        this.clips = Map.copyOf(clips);
    }

    public static AnimationLibrary load() {
        Map<String, RunClip> clips = new LinkedHashMap<>();
        try {
            Identifier indexId = Identifier.fromNamespaceAndPath(
                    "player_model", "animations/index.json");
            InputStream stream = Minecraft.getInstance().getResourceManager()
                    .getResource(indexId)
                    .map(resource -> {
                        try {
                            return resource.open();
                        } catch (Exception exception) {
                            throw new RuntimeException(exception);
                        }
                    })
                    .orElseGet(() -> AnimationLibrary.class.getResourceAsStream(
                            "/assets/player_model/animations/index.json"));
            if (stream == null) {
                throw new IllegalStateException("animations/index.json is missing");
            }

            try (BufferedReader reader = new BufferedReader(
                    new InputStreamReader(stream, StandardCharsets.UTF_8))) {
                JsonObject root = JsonParser.parseReader(reader).getAsJsonObject();
                JsonArray entries = root.getAsJsonArray("clips");
                for (JsonElement element : entries) {
                    JsonObject entry = element.getAsJsonObject();
                    String name = entry.get("name").getAsString();
                    String file = entry.get("file").getAsString();
                    RunClip clip = RunClip.load(name, file);
                    if (clip != null) {
                        clips.put(name.toLowerCase(), clip);
                    }
                }
            }
        } catch (Exception exception) {
            LOGGER.error("[player_model] failed to load animation index", exception);
        }

        if (clips.isEmpty()) {
            RunClip run = RunClip.load("run", "run.json");
            if (run != null) {
                clips.put("run", run);
            }
        }
        LOGGER.info("[player_model] loaded {} animation clips", clips.size());
        return new AnimationLibrary(clips);
    }

    public RunClip select(AvatarRenderState state) {
        boolean moving = state.walkAnimationSpeed > 0.02F;
        if (moving) {
            RunClip run = clips.get("run");
            if (run != null) return run;
            RunClip walk = clips.get("walk");
            if (walk != null) return walk;
        } else {
            RunClip idle = clips.get("idle");
            if (idle != null) return idle;
        }

        if (!clips.isEmpty()) {
            return clips.values().iterator().next();
        }
        return null;
    }
}
