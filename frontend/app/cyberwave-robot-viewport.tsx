"use client";

import { useEffect, useRef, useState } from "react";
import type { Object3D, WebGLRenderer } from "three";
import type { URDFRobot } from "urdf-loader";

type ViewMode = "reset" | "orbit";
export type RobotGesture = "assess" | "guide" | "caution";

type Props = {
  action: string;
  moving: boolean;
  commandSequence?: number;
  commandGesture?: RobotGesture;
  agentWorking?: boolean;
  viewMode?: ViewMode;
  compact?: boolean;
};

type RobotPose = {
  shoulder_pan: number;
  shoulder_lift: number;
  elbow_flex: number;
  wrist_flex: number;
  wrist_roll: number;
  gripper: number;
};

type RobotMotion = {
  startedAt: number;
  from: RobotPose;
  accent: RobotPose;
  target: RobotPose;
  accentDuration: number;
  settleDuration: number;
  settleStartedAt: number | null;
  holdForAgent: boolean;
};

const SAFE_POSE = {
  shoulder_pan: 0.3,
  shoulder_lift: -0.85,
  elbow_flex: 1.1,
  wrist_flex: 0.2,
  wrist_roll: 0,
  gripper: 0.08,
} satisfies RobotPose;

const POINT_POSE = {
  shoulder_pan: -0.45,
  shoulder_lift: -1.05,
  elbow_flex: 0.72,
  wrist_flex: -0.42,
  wrist_roll: 0.2,
  gripper: 1.35,
} satisfies RobotPose;

const ASSESS_POSE = {
  shoulder_pan: 0.12,
  shoulder_lift: -0.72,
  elbow_flex: 0.95,
  wrist_flex: 0.38,
  wrist_roll: 0,
  gripper: 0.62,
} satisfies RobotPose;

const GUIDE_POSE = {
  shoulder_pan: 0.08,
  shoulder_lift: -0.78,
  elbow_flex: 1.02,
  wrist_flex: 0.06,
  wrist_roll: 0.14,
  gripper: 1.15,
} satisfies RobotPose;

const CAUTION_POSE = {
  shoulder_pan: 0,
  shoulder_lift: -0.48,
  elbow_flex: 0.72,
  wrist_flex: 0.62,
  wrist_roll: 0,
  gripper: 0.02,
} satisfies RobotPose;

const POSE_JOINTS = Object.keys(SAFE_POSE) as Array<keyof RobotPose>;

function easeInOut(value: number) {
  const clamped = Math.max(0, Math.min(1, value));
  return clamped < 0.5 ? 2 * clamped * clamped : 1 - Math.pow(-2 * clamped + 2, 2) / 2;
}

function interpolatePose(from: RobotPose, to: RobotPose, progress: number): RobotPose {
  const eased = easeInOut(progress);
  return Object.fromEntries(POSE_JOINTS.map((joint) => [joint, from[joint] + (to[joint] - from[joint]) * eased])) as RobotPose;
}

export default function CyberwaveRobotViewport({ action, moving, commandSequence = 0, commandGesture = "assess", agentWorking = false, viewMode = "reset", compact = false }: Props) {
  const hostRef = useRef<HTMLDivElement>(null);
  const robotRef = useRef<URDFRobot | null>(null);
  const controlsRef = useRef<{ autoRotate: boolean; autoRotateSpeed: number; update: () => void } | null>(null);
  const actionRef = useRef(action);
  const movingRef = useRef(moving);
  const viewModeRef = useRef(viewMode);
  const basePoseRef = useRef<RobotPose>({ ...SAFE_POSE });
  const currentPoseRef = useRef<RobotPose>({ ...SAFE_POSE });
  const motionRef = useRef<RobotMotion | null>(null);
  const lastCommandSequenceRef = useRef(commandSequence);
  const agentWorkingRef = useRef(agentWorking);
  const [ready, setReady] = useState(false);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    agentWorkingRef.current = agentWorking;
  }, [agentWorking]);

  useEffect(() => {
    actionRef.current = action;
    movingRef.current = moving;
    const robot = robotRef.current;
    const pose = action === "POINT_TO_TOOL" || moving ? POINT_POSE : SAFE_POSE;
    basePoseRef.current = { ...pose };
    if (!robot || motionRef.current) return;
    motionRef.current = {
      startedAt: performance.now(),
      from: { ...currentPoseRef.current },
      accent: { ...pose },
      target: { ...pose },
      accentDuration: 1,
      settleDuration: 650,
      settleStartedAt: performance.now(),
      holdForAgent: false,
    };
  }, [action, moving, ready]);

  useEffect(() => {
    if (commandSequence === lastCommandSequenceRef.current) return;
    lastCommandSequenceRef.current = commandSequence;
    if (!robotRef.current) return;
    const target = basePoseRef.current;
    const accent = commandGesture === "guide" ? GUIDE_POSE : commandGesture === "caution" ? CAUTION_POSE : ASSESS_POSE;
    motionRef.current = {
      startedAt: performance.now(),
      from: { ...currentPoseRef.current },
      accent: { ...accent },
      target: { ...target },
      accentDuration: commandGesture === "caution" ? 520 : 680,
      settleDuration: commandGesture === "guide" ? 900 : 720,
      settleStartedAt: null,
      holdForAgent: true,
    };
  }, [commandGesture, commandSequence, ready]);

  useEffect(() => {
    viewModeRef.current = viewMode;
    if (!controlsRef.current) return;
    controlsRef.current.autoRotate = viewMode === "orbit";
    controlsRef.current.autoRotateSpeed = compact ? 0.75 : 0.45;
  }, [viewMode, compact]);

  useEffect(() => {
    const host = hostRef.current;
    if (!host) return;
    let renderer: WebGLRenderer | null = null;
    let frame = 0;
    let disposed = false;
    let observer: ResizeObserver | null = null;
    let sceneRoot: Object3D | null = null;

    const initialize = async () => {
      try {
        const THREE = await import("three");
        const [{ OrbitControls }, { default: URDFLoader }] = await Promise.all([
          import("three/examples/jsm/controls/OrbitControls.js"),
          import("urdf-loader"),
        ]);
        if (disposed) return;

        const scene = new THREE.Scene();
        scene.background = new THREE.Color(compact ? 0xdde2df : 0xe7eae8);
        scene.fog = new THREE.Fog(compact ? 0xdde2df : 0xe7eae8, 1.7, 3.5);
        sceneRoot = scene;

        const camera = new THREE.PerspectiveCamera(compact ? 26 : 30, 1, 0.01, 30);
        renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false, powerPreference: "high-performance" });
        renderer.setPixelRatio(Math.min(window.devicePixelRatio, compact ? 1.25 : 1.75));
        renderer.outputColorSpace = THREE.SRGBColorSpace;
        renderer.toneMapping = THREE.ACESFilmicToneMapping;
        renderer.toneMappingExposure = 0.92;
        renderer.shadowMap.enabled = !compact;
        renderer.shadowMap.type = THREE.PCFShadowMap;
        host.appendChild(renderer.domElement);

        const controls = new OrbitControls(camera, renderer.domElement);
        controls.enableDamping = true;
        controls.dampingFactor = 0.06;
        controls.enablePan = false;
        controls.enableZoom = !compact;
        controls.minPolarAngle = Math.PI * 0.18;
        controls.maxPolarAngle = Math.PI * 0.57;
        controls.autoRotate = viewModeRef.current === "orbit" || compact;
        controls.autoRotateSpeed = compact ? 0.75 : 0.45;
        controlsRef.current = controls;

        scene.add(new THREE.HemisphereLight(0xffffff, 0x748078, compact ? 1.65 : 1.85));
        const key = new THREE.DirectionalLight(0xffffff, 2.35);
        key.position.set(1.8, 2.4, 1.6);
        key.castShadow = !compact;
        key.shadow.mapSize.set(1024, 1024);
        scene.add(key);
        const rim = new THREE.DirectionalLight(0xc7e7db, 0.85);
        rim.position.set(-1.4, 1.1, -1.8);
        scene.add(rim);

        const floor = new THREE.Mesh(
          new THREE.PlaneGeometry(4, 4),
          new THREE.MeshStandardMaterial({ color: compact ? 0xd9dedb : 0xe1e5e2, roughness: 0.92, metalness: 0.02 }),
        );
        floor.rotation.x = -Math.PI / 2;
        floor.receiveShadow = true;
        scene.add(floor);
        const grid = new THREE.GridHelper(3.5, 18, 0xb7c0bb, 0xcdd3d0);
        grid.material.opacity = compact ? 0.16 : 0.24;
        grid.material.transparent = true;
        grid.position.y = 0.001;
        scene.add(grid);

        const manager = new THREE.LoadingManager();
        const meshesReady = new Promise<void>((resolve) => { manager.onLoad = resolve; });
        const loader = new URDFLoader(manager);
        const robot = await loader.loadAsync("/robots/so101/so101.urdf");
        if (disposed) return;
        robot.rotation.x = -Math.PI / 2;
        robot.traverse((child) => {
          const mesh = child as THREE.Mesh;
          if (mesh.isMesh) {
            mesh.castShadow = !compact;
            mesh.receiveShadow = true;
          }
        });
        scene.add(robot);
        robotRef.current = robot;

        const applyPose = () => {
          const pose = actionRef.current === "POINT_TO_TOOL" || movingRef.current ? POINT_POSE : SAFE_POSE;
          basePoseRef.current = { ...pose };
          currentPoseRef.current = { ...pose };
          for (const [joint, value] of Object.entries(pose)) robot.joints[joint]?.setJointValue(value);
        };

        await meshesReady;
        let geometryBounds = new THREE.Box3().setFromObject(robot);
        let geometrySize = geometryBounds.getSize(new THREE.Vector3());
        for (let attempt = 0; attempt < 40 && Math.max(geometrySize.x, geometrySize.y, geometrySize.z) < 0.01; attempt += 1) {
          await new Promise<void>((resolve) => window.setTimeout(resolve, 50));
          geometryBounds = new THREE.Box3().setFromObject(robot);
          geometrySize = geometryBounds.getSize(new THREE.Vector3());
        }
        if (disposed) return;
        applyPose();
        const box = new THREE.Box3().setFromObject(robot);
        if (Math.max(geometrySize.x, geometrySize.y, geometrySize.z) < 0.01) throw new Error("SO-101 geometry did not load");
        robot.position.y -= box.min.y;
        const fitted = new THREE.Box3().setFromObject(robot);
        const center = fitted.getCenter(new THREE.Vector3());
        const size = fitted.getSize(new THREE.Vector3());
        const radius = Math.max(size.x, size.y, size.z);
        camera.position.set(center.x + radius * 1.3, center.y + radius * 0.72, center.z + radius * 1.55);
        controls.target.set(center.x, center.y + radius * 0.05, center.z);
        camera.near = Math.max(0.002, radius / 100);
        camera.far = radius * 24;
        camera.updateProjectionMatrix();
        controls.update();
        setReady(true);

        const resize = () => {
          if (!renderer) return;
          const width = Math.max(1, host.clientWidth);
          const height = Math.max(1, host.clientHeight);
          renderer.setSize(width, height, false);
          camera.aspect = width / height;
          camera.updateProjectionMatrix();
        };
        observer = new ResizeObserver(resize);
        observer.observe(host);
        resize();

        const render = () => {
          if (disposed || !renderer) return;
          const motion = motionRef.current;
          if (motion) {
            const now = performance.now();
            const elapsed = now - motion.startedAt;
            let pose = motion.accent;
            if (elapsed <= motion.accentDuration) {
              pose = interpolatePose(motion.from, motion.accent, elapsed / motion.accentDuration);
            } else if (!(motion.holdForAgent && agentWorkingRef.current)) {
              if (motion.settleStartedAt === null) motion.settleStartedAt = now;
              pose = interpolatePose(motion.accent, motion.target, (now - motion.settleStartedAt) / motion.settleDuration);
            }
            currentPoseRef.current = pose;
            for (const [joint, value] of Object.entries(pose)) robot.joints[joint]?.setJointValue(value);
            if (motion.settleStartedAt !== null && now - motion.settleStartedAt >= motion.settleDuration) {
              currentPoseRef.current = { ...motion.target };
              motionRef.current = null;
            }
          }
          controls.update();
          renderer.render(scene, camera);
          frame = requestAnimationFrame(render);
        };
        render();
      } catch {
        if (!disposed) setFailed(true);
      }
    };

    initialize();
    return () => {
      disposed = true;
      cancelAnimationFrame(frame);
      observer?.disconnect();
      controlsRef.current = null;
      robotRef.current = null;
      if (sceneRoot) {
        sceneRoot.traverse((child) => {
          const mesh = child as { geometry?: { dispose: () => void }; material?: { dispose: () => void } | Array<{ dispose: () => void }> };
          mesh.geometry?.dispose();
          if (Array.isArray(mesh.material)) mesh.material.forEach((material) => material.dispose());
          else mesh.material?.dispose();
        });
      }
      renderer?.dispose();
      renderer?.domElement.remove();
    };
  }, [compact]);

  return <div ref={hostRef} className={`cyberwave-robot-canvas ${compact ? "compact" : ""}`} aria-label="Cyberwave SO-101 digital twin">
    {!ready && !failed && <div className="robot-loading"><i></i><span>Loading SO-101 twin…</span></div>}
    {failed && <div className="robot-loading failed"><span>SO-101 model unavailable</span></div>}
  </div>;
}
