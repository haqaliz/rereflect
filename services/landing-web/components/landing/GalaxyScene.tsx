'use client';

import { useMemo, useRef } from 'react';
import * as THREE from 'three';
import { Canvas, useFrame } from '@react-three/fiber';
import { OrbitControls } from '@react-three/drei';
import { EffectComposer, Bloom } from '@react-three/postprocessing';
import { galaxyState } from '@/lib/landing/scrollState';

const SENTIMENT_COLORS = ['#ff8a5c', '#ffc46b', '#ff4d5e'];
const CLUSTER_CENTERS: [number, number, number][] = [
  [-2.5, 0.7, -0.4],
  [0, -0.9, 0.9],
  [2.5, 0.7, -0.4],
];
const RATIOS = [0.52, 0.31, 0.17];

function gaussian() {
  let u = 0;
  let v = 0;
  while (u === 0) u = Math.random();
  while (v === 0) v = Math.random();
  return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v);
}

function buildGalaxy(count: number) {
  const a = new Float32Array(count * 3);
  const b = new Float32Array(count * 3);
  const colors = new Float32Array(count * 3);
  const speeds = new Float32Array(count);
  const palette = SENTIMENT_COLORS.map((c) => new THREE.Color(c));
  const scratch = new THREE.Color();

  for (let i = 0; i < count; i++) {
    const r = Math.pow(Math.random(), 0.55) * 4.4;
    const theta = Math.random() * Math.PI * 2;
    const phi = Math.acos(2 * Math.random() - 1);
    const arm = Math.random() < 0.5 ? 1 : -1;

    a[i * 3] = r * Math.sin(phi) * Math.cos(theta) + Math.sin(theta * 3 + arm) * 0.4;
    a[i * 3 + 1] = r * Math.sin(phi) * Math.sin(theta) * 0.3 + Math.cos(theta * 2 + arm * 0.6) * 0.35;
    a[i * 3 + 2] = r * Math.cos(phi) * 0.85;

    let s = 0;
    const roll = Math.random();
    let acc = 0;
    for (let k = 0; k < RATIOS.length; k++) {
      acc += RATIOS[k];
      if (roll <= acc) {
        s = k;
        break;
      }
    }
    const c = CLUSTER_CENTERS[s];
    const g = gaussian();
    b[i * 3] = c[0] + g * 0.9;
    b[i * 3 + 1] = c[1] + g * 0.75;
    b[i * 3 + 2] = c[2] + g * 0.75;

    const col = scratch.copy(palette[s]).multiplyScalar(0.6 + Math.random() * 0.45);
    colors[i * 3] = col.r;
    colors[i * 3 + 1] = col.g;
    colors[i * 3 + 2] = col.b;

    const inner = 1 - Math.min(r / 4.4, 1);
    speeds[i] = (0.1 + inner * 0.3) * (Math.random() < 0.5 ? 1 : -1);
  }

  return { a, b, colors, speeds };
}

function Starfield() {
  const groupRef = useRef<THREE.Group>(null);
  const pointsRef = useRef<THREE.Points | null>(null);

  useFrame((_, delta) => {
    const g = groupRef.current;
    if (!g) return;

    if (!pointsRef.current) {
      const count = 260;
      const positions = new Float32Array(count * 3);
      for (let i = 0; i < count; i++) {
        const r = 13 + Math.random() * 6;
        const theta = Math.random() * Math.PI * 2;
        const phi = Math.acos(2 * Math.random() - 1);
        positions[i * 3] = r * Math.sin(phi) * Math.cos(theta);
        positions[i * 3 + 1] = r * Math.sin(phi) * Math.sin(theta);
        positions[i * 3 + 2] = r * Math.cos(phi);
      }
      const geometry = new THREE.BufferGeometry();
      geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));
      const material = new THREE.PointsMaterial({
        size: 0.045,
        sizeAttenuation: true,
        transparent: true,
        depthWrite: false,
        blending: THREE.AdditiveBlending,
        opacity: 0.18,
        color: '#ffffff',
      });
      pointsRef.current = new THREE.Points(geometry, material);
      pointsRef.current.frustumCulled = false;
      g.add(pointsRef.current);
    }

    g.rotation.y -= delta * 0.005;
  });

  return <group ref={groupRef} />;
}

function GalaxyPoints({ count }: { count: number }) {
  const groupRef = useRef<THREE.Group>(null);
  const pointsRef = useRef<THREE.Points | null>(null);
  const dataRef = useRef<{ a: Float32Array; b: Float32Array; speeds: Float32Array } | null>(null);
  const t = useRef(0);

  useFrame((state, delta) => {
    const g = groupRef.current;
    if (!g) return;

    if (!pointsRef.current) {
      const data = buildGalaxy(count);
      const geometry = new THREE.BufferGeometry();
      geometry.setAttribute('position', new THREE.BufferAttribute(new Float32Array(count * 3), 3));
      geometry.setAttribute('color', new THREE.BufferAttribute(data.colors, 3));
      const material = new THREE.PointsMaterial({
        size: 0.032,
        sizeAttenuation: true,
        vertexColors: true,
        transparent: true,
        depthWrite: false,
        blending: THREE.AdditiveBlending,
        opacity: 0.68,
      });
      pointsRef.current = new THREE.Points(geometry, material);
      pointsRef.current.frustumCulled = false;
      g.add(pointsRef.current);
      dataRef.current = data;
    }

    const geometry = pointsRef.current.geometry;
    const pos = geometry.attributes.position.array as Float32Array;
    const data = dataRef.current!;

    t.current = THREE.MathUtils.damp(t.current, galaxyState.t, 6, delta);
    const s = t.current;
    for (let i = 0; i < pos.length; i += 3) {
      pos[i] = data.a[i] + (data.b[i] - data.a[i]) * s;
      pos[i + 1] = data.a[i + 1] + (data.b[i + 1] - data.a[i + 1]) * s;
      pos[i + 2] = data.a[i + 2] + (data.b[i + 2] - data.a[i + 2]) * s;
    }

    for (let i = 0; i < pos.length; i += 3) {
      const speed = data.speeds[i / 3] * delta;
      const ca = Math.cos(speed);
      const sa = Math.sin(speed);
      const px = pos[i];
      const pz = pos[i + 2];
      pos[i] = px * ca - pz * sa;
      pos[i + 2] = px * sa + pz * ca;
    }
    geometry.attributes.position.needsUpdate = true;

    g.rotation.y += delta * 0.03;
    const targetScale = 0.55 + galaxyState.intro * 0.45;
    g.scale.setScalar(THREE.MathUtils.damp(g.scale.x, targetScale, 4, delta));

    state.camera.lookAt(0, 0, 0);
  });

  return <group ref={groupRef} />;
}

export default function GalaxyScene() {
  const count = useMemo(
    () => (typeof window !== 'undefined' && window.innerWidth < 768 ? 650 : 1400),
    [],
  );

  return (
    <Canvas
      dpr={[1, 1.75]}
      camera={{ position: [0, 0, 7], fov: 42 }}
      gl={{ antialias: true, alpha: true, powerPreference: 'high-performance' }}
      style={{ position: 'absolute', inset: 0 }}
    >
      <GalaxyPoints count={count} />
      <Starfield />
      <OrbitControls
        makeDefault
        enableZoom={false}
        enablePan={false}
        enableDamping
        dampingFactor={0.06}
        autoRotate
        autoRotateSpeed={0.7}
        rotateSpeed={0.5}
      />
      <EffectComposer multisampling={0}>
        <Bloom
          mipmapBlur
          intensity={0.8}
          luminanceThreshold={0.12}
          luminanceSmoothing={0.25}
          radius={0.72}
        />
      </EffectComposer>
    </Canvas>
  );
}