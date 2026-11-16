package com.playermodel.client;

import com.google.gson.JsonArray;
import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import com.google.gson.JsonParser;
import net.minecraft.client.Minecraft;
import net.minecraft.client.model.geom.ModelPart;
import net.minecraft.resources.Identifier;
import org.joml.Quaternionf;
import org.joml.Vector3f;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.io.BufferedReader;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

public final class RunClip {
    private static final Logger LOGGER = LoggerFactory.getLogger("player_model");
    private static final Quaternionf IDENTITY = new Quaternionf();
    private final String name;

    private final List<Frame> frames;

    private RunClip(String name, List<Frame> frames) {
        this.name = name;
        this.frames = frames;
    }

    public static RunClip loadOrFallback() {
        RunClip clip = load("run", "run.json");
        return clip != null ? clip : new RunClip("empty", List.of());
    }

    public static RunClip load(String displayName, String fileName) {
        try {
            Identifier resourceId = Identifier.fromNamespaceAndPath(
                    "player_model", "animations/" + fileName);
            InputStream stream = Minecraft.getInstance().getResourceManager()
                    .getResource(resourceId)
                    .map(resource -> {
                        try {
                            return resource.open();
                        } catch (Exception exception) {
                            throw new RuntimeException(exception);
                        }
                    })
                    .orElseGet(() -> RunClip.class.getResourceAsStream(
                            "/assets/player_model/animations/" + fileName));
            if (stream == null) {
                throw new IllegalStateException(fileName + " is missing from the mod jar");
            }

            try (BufferedReader reader = new BufferedReader(
                    new InputStreamReader(stream, StandardCharsets.UTF_8))) {
                JsonObject root = JsonParser.parseReader(reader).getAsJsonObject();
                JsonArray keyArray = root.getAsJsonArray("keys");
                List<Frame> frames = new ArrayList<>();
                for (JsonElement keyElement : keyArray) {
                    JsonObject key = keyElement.getAsJsonObject();
                    float phase = key.get("phase").getAsFloat();
                    JsonObject bones = key.getAsJsonObject("bones");
                    Map<String, Quaternionf> transforms = new LinkedHashMap<>();
                    for (Map.Entry<String, JsonElement> entry : bones.entrySet()) {
                        JsonArray values = entry.getValue().getAsJsonArray();
                        transforms.put(entry.getKey(), new Quaternionf(
                                values.get(1).getAsFloat(),
                                values.get(2).getAsFloat(),
                                values.get(3).getAsFloat(),
                                values.get(0).getAsFloat()).normalize());
                    }
                    Map<String, Vector3f> locations = new LinkedHashMap<>();
                    JsonObject locationObject = key.has("locations")
                            ? key.getAsJsonObject("locations")
                            : null;
                    if (locationObject != null) {
                        for (Map.Entry<String, JsonElement> entry : locationObject.entrySet()) {
                            JsonArray values = entry.getValue().getAsJsonArray();
                            locations.put(entry.getKey(), new Vector3f(
                                    values.get(0).getAsFloat(),
                                    values.get(1).getAsFloat(),
                                    values.get(2).getAsFloat()));
                        }
                    }
                    frames.add(new Frame(phase, transforms, locations));
                }
                if (frames.size() < 2) {
                    throw new IllegalStateException(fileName + " needs at least two key frames");
                }
                LOGGER.info("[player_model] loaded {} with {} key frames", displayName, frames.size());
                return new RunClip(displayName, List.copyOf(frames));
            }
        } catch (Exception exception) {
            LOGGER.error("[player_model] failed to load animation {}", fileName, exception);
            return null;
        }
    }

    public String name() {
        return name;
    }

    public void apply(Map<String, ModelPart> parts, float phase, float blend) {
        if (frames.isEmpty()) {
            return;
        }

        Frame first = frames.get(0);
        Frame last = frames.get(frames.size() - 1);
        Frame from = last;
        Frame to = first;
        float local = 0.0F;

        for (int index = 0; index < frames.size() - 1; index++) {
            Frame current = frames.get(index);
            Frame next = frames.get(index + 1);
            if (phase >= current.phase && phase <= next.phase) {
                from = current;
                to = next;
                local = (phase - current.phase) / Math.max(0.000001F, next.phase - current.phase);
                break;
            }
        }

        for (Map.Entry<String, ModelPart> entry : parts.entrySet()) {
            String bone = entry.getKey();
            Quaternionf a = from.bones.get(bone);
            Quaternionf b = to.bones.get(bone);
            if (a == null || b == null) {
                continue;
            }

            Quaternionf sampled = new Quaternionf(a).slerp(b, local);
            Quaternionf blended = new Quaternionf(IDENTITY).slerp(sampled, blend).normalize();
            entry.getValue().rotateBy(blended);

            Vector3f locationA = from.locations.get(bone);
            Vector3f locationB = to.locations.get(bone);
            if (locationA != null && locationB != null) {
                Vector3f location = new Vector3f(locationA).lerp(locationB, local).mul(blend * 16.0F);
                entry.getValue().x += location.x;
                entry.getValue().y += location.y;
                entry.getValue().z += location.z;
            }
        }
    }

    private record Frame(
            float phase,
            Map<String, Quaternionf> bones,
            Map<String, Vector3f> locations) {
    }
}
