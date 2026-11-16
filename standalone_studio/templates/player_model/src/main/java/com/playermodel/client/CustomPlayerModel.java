package com.playermodel.client;

import net.minecraft.client.model.EntityModel;
import net.minecraft.client.model.geom.ModelPart;
import net.minecraft.client.model.geom.PartPose;
import net.minecraft.client.model.geom.builders.CubeDeformation;
import net.minecraft.client.model.geom.builders.CubeListBuilder;
import net.minecraft.client.model.geom.builders.LayerDefinition;
import net.minecraft.client.model.geom.builders.MeshDefinition;
import net.minecraft.client.model.geom.builders.PartDefinition;
import net.minecraft.client.renderer.entity.state.AvatarRenderState;
import net.minecraft.client.renderer.rendertype.RenderTypes;

import java.util.Map;
import java.util.function.Function;

public final class CustomPlayerModel extends EntityModel<AvatarRenderState> {
    private static final CubeDeformation OVERLAY = new CubeDeformation(0.25F);
    private static final CubeDeformation HAT = new CubeDeformation(0.5F);

    private final Map<String, ModelPart> parts;
    private final AnimationLibrary animations;

    public CustomPlayerModel(ModelPart root, AnimationLibrary animations) {
        super(root, RenderTypes::entityCutout);
        Function<String, ModelPart> lookup = root.createPartLookup();
        this.parts = Map.ofEntries(
                Map.entry("spine", lookup.apply("spine")),
                Map.entry("chest", lookup.apply("chest")),
                Map.entry("head", lookup.apply("head")),
                Map.entry("upper_arm.L", lookup.apply("upper_arm.L")),
                Map.entry("forearm.L", lookup.apply("forearm.L")),
                Map.entry("upper_arm.R", lookup.apply("upper_arm.R")),
                Map.entry("forearm.R", lookup.apply("forearm.R")),
                Map.entry("thigh.L", lookup.apply("thigh.L")),
                Map.entry("shin.L", lookup.apply("shin.L")),
                Map.entry("thigh.R", lookup.apply("thigh.R")),
                Map.entry("shin.R", lookup.apply("shin.R")));
        this.animations = animations;
    }

    public static LayerDefinition createLayer(boolean slim) {
        MeshDefinition mesh = new MeshDefinition();
        PartDefinition root = mesh.getRoot();
        int armWidth = slim ? 3 : 4;

        PartDefinition hips = root.addOrReplaceChild(
                "hips", CubeListBuilder.create(), PartPose.offset(0.0F, 12.0F, 0.0F));

        PartDefinition spine = hips.addOrReplaceChild(
                "spine",
                CubeListBuilder.create().texOffs(16, 22).addBox(-4.0F, -6.0F, -2.0F, 8.0F, 6.0F, 4.0F),
                PartPose.ZERO);
        spine.addOrReplaceChild(
                "spine_overlay",
                CubeListBuilder.create().texOffs(16, 38)
                        .addBox(-4.0F, -6.0F, -2.0F, 8.0F, 6.0F, 4.0F, OVERLAY),
                PartPose.ZERO);

        PartDefinition chest = spine.addOrReplaceChild(
                "chest",
                CubeListBuilder.create().texOffs(16, 16).addBox(-4.0F, -6.0F, -2.0F, 8.0F, 6.0F, 4.0F),
                PartPose.offset(0.0F, -6.0F, 0.0F));
        chest.addOrReplaceChild(
                "chest_overlay",
                CubeListBuilder.create().texOffs(16, 32)
                        .addBox(-4.0F, -6.0F, -2.0F, 8.0F, 6.0F, 4.0F, OVERLAY),
                PartPose.ZERO);

        PartDefinition head = chest.addOrReplaceChild(
                "head",
                CubeListBuilder.create().texOffs(0, 0).addBox(-4.0F, -8.0F, -4.0F, 8.0F, 8.0F, 8.0F),
                PartPose.offset(0.0F, -6.0F, 0.0F));
        head.addOrReplaceChild(
                "hat",
                CubeListBuilder.create().texOffs(32, 0)
                        .addBox(-4.0F, -8.0F, -4.0F, 8.0F, 8.0F, 8.0F, HAT),
                PartPose.ZERO);

        addArm(chest, true, slim, armWidth);
        addArm(chest, false, slim, armWidth);
        addLeg(hips, true);
        addLeg(hips, false);

        return LayerDefinition.create(mesh, 64, 64);
    }

    private static void addArm(PartDefinition chest, boolean right, boolean slim, int armWidth) {
        String upperName = right ? "upper_arm.R" : "upper_arm.L";
        String lowerName = right ? "forearm.R" : "forearm.L";
        float pivotX = right ? -5.0F : 5.0F;
        float cubeX = right ? -2.0F : -1.0F;
        int baseU = right ? 40 : 32;
        int baseV = right ? 16 : 48;

        PartDefinition upper = chest.addOrReplaceChild(
                upperName,
                CubeListBuilder.create().texOffs(baseU, baseV)
                        .addBox(cubeX, -2.0F, -2.0F, armWidth, 6.0F, 4.0F),
                PartPose.offset(pivotX, -4.0F, 0.0F));
        upper.addOrReplaceChild(
                upperName + "_overlay",
                CubeListBuilder.create().texOffs(right ? 40 : 48, right ? 32 : 48)
                        .addBox(cubeX, -2.0F, -2.0F, armWidth, 6.0F, 4.0F, OVERLAY),
                PartPose.ZERO);

        PartDefinition lower = upper.addOrReplaceChild(
                lowerName,
                CubeListBuilder.create().texOffs(baseU, baseV + 6)
                        .addBox(cubeX, 0.0F, -2.0F, armWidth, 6.0F, 4.0F),
                PartPose.offset(0.0F, 4.0F, 0.0F));
        lower.addOrReplaceChild(
                lowerName + "_overlay",
                CubeListBuilder.create().texOffs(right ? 40 : 48, (right ? 32 : 48) + 6)
                        .addBox(cubeX, 0.0F, -2.0F, armWidth, 6.0F, 4.0F, OVERLAY),
                PartPose.ZERO);
    }

    private static void addLeg(PartDefinition hips, boolean right) {
        String upperName = right ? "thigh.R" : "thigh.L";
        String lowerName = right ? "shin.R" : "shin.L";
        float pivotX = right ? -1.9F : 1.9F;
        int baseU = right ? 0 : 16;
        int baseV = right ? 16 : 48;

        PartDefinition upper = hips.addOrReplaceChild(
                upperName,
                CubeListBuilder.create().texOffs(baseU, baseV)
                        .addBox(-2.0F, 0.0F, -2.0F, 4.0F, 6.0F, 4.0F),
                PartPose.offset(pivotX, 0.0F, 0.0F));
        upper.addOrReplaceChild(
                upperName + "_overlay",
                CubeListBuilder.create().texOffs(right ? 0 : 0, right ? 32 : 48)
                        .addBox(-2.0F, 0.0F, -2.0F, 4.0F, 6.0F, 4.0F, OVERLAY),
                PartPose.ZERO);

        PartDefinition lower = upper.addOrReplaceChild(
                lowerName,
                CubeListBuilder.create().texOffs(baseU, baseV + 6)
                        .addBox(-2.0F, 0.0F, -2.0F, 4.0F, 6.0F, 4.0F),
                PartPose.offset(0.0F, 6.0F, 0.0F));
        lower.addOrReplaceChild(
                lowerName + "_overlay",
                CubeListBuilder.create().texOffs(right ? 0 : 0, (right ? 32 : 48) + 6)
                        .addBox(-2.0F, 0.0F, -2.0F, 4.0F, 6.0F, 4.0F, OVERLAY),
                PartPose.ZERO);
    }

    @Override
    public void setupAnim(AvatarRenderState state) {
        resetPose();

        float movement = Math.max(0.0F, Math.min(1.0F, state.walkAnimationSpeed));
        if (movement < 0.02F) {
            return;
        }

        float phase = (state.walkAnimationPos * 0.6662F) / (float) (Math.PI * 2.0);
        phase -= (float) Math.floor(phase);
        float blend = Math.min(1.0F, movement * 4.0F);
        RunClip clip = animations.select(state);
        if (clip != null) {
            clip.apply(parts, phase, blend);
        }
    }
}
