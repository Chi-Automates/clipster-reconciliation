import React from "react";
import {
  AbsoluteFill,
  Composition,
  Easing,
  Html5Audio,
  Img,
  OffthreadVideo,
  Sequence,
  continueRender,
  delayRender,
  interpolate,
  random,
  spring,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";

// ---------- brand ----------
const NAVY = "#0F172A";
const CREAM = "#F5F3E7";
const BLUE = "#2563EB";
const GOLD = "#FACC15";
const PINK = "#EC4899";
const HEAD = "'Baloo 2'";
const BODY = "Nunito";
const FPS = 30;
const s = (sec: number) => Math.round(sec * FPS);

// ---------- fonts ----------
if (typeof document !== "undefined") {
  const fonts: [string, string, string][] = [
    ["Baloo 2", "800", "fonts/baloo-2-latin-800-normal.woff2"],
    [BODY, "700", "fonts/nunito-latin-700-normal.woff2"],
    [BODY, "800", "fonts/nunito-latin-800-normal.woff2"],
    [BODY, "900", "fonts/nunito-latin-900-normal.woff2"],
  ];
  const handle = delayRender("fonts");
  Promise.all(
    fonts.map(([family, weight, file]) => {
      const f = new FontFace(family, `url(${staticFile(file)})`, { weight });
      return f.load().then((l) => document.fonts.add(l));
    }),
  ).then(() => continueRender(handle));
}

// ---------- timeline (frames) ----------
const T = {
  s1: 0,
  s2: s(7.5),
  s3: s(15),
  s4: s(24),
  s5: s(32),
  s6: s(40) - 8,
  s7: s(44),
  s8: s(51) - 8,
  end: s(56.9),
  total: s(66),
};

// ---------- helpers ----------
const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;

const usePop = (from: number, to?: number) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const inn = spring({ frame: frame - from, fps, config: { damping: 11, stiffness: 190, mass: 0.7 } });
  const out = to === undefined ? 1 : interpolate(frame, [to - 5, to], [1, 0], clamp);
  return { visible: frame >= from && (to === undefined || frame < to), scale: inn * (0.85 + 0.15 * out), opacity: Math.min(1, inn * 2) * out };
};

const Pop: React.FC<{ from: number; to?: number; children: React.ReactNode; style?: React.CSSProperties; rotate?: number }> = ({ from, to, children, style, rotate = 0 }) => {
  const p = usePop(from, to);
  if (!p.visible) return null;
  return <div style={{ transform: `scale(${p.scale}) rotate(${rotate}deg)`, opacity: p.opacity, ...style }}>{children}</div>;
};

/** Headline with a thick outline and a hard drop shadow. */
const Txt: React.FC<{ children: React.ReactNode; size: number; color?: string; stroke?: string; sw?: number; shadow?: string; font?: string; weight?: number; ls?: number }> = ({
  children,
  size,
  color = CREAM,
  stroke = NAVY,
  sw = 18,
  shadow = "rgba(15,23,42,0.45)",
  font = HEAD,
  weight = 800,
  ls = 0,
}) => {
  const base: React.CSSProperties = { fontFamily: font, fontWeight: weight, fontSize: size, lineHeight: 1.02, letterSpacing: ls, whiteSpace: "nowrap", textAlign: "center" };
  return (
    <div style={{ position: "relative", display: "inline-block", filter: `drop-shadow(0 ${Math.round(size * 0.08)}px 0 ${shadow})` }}>
      <div style={{ ...base, color: stroke, WebkitTextStroke: `${sw}px ${stroke}` }}>{children}</div>
      <div style={{ ...base, color, position: "absolute", inset: 0 }}>{children}</div>
    </div>
  );
};

const Chip: React.FC<{ children: React.ReactNode; bg?: string; color?: string; size?: number; border?: string; font?: string }> = ({ children, bg = NAVY, color = CREAM, size = 50, border, font = HEAD }) => (
  <div
    style={{
      display: "inline-block",
      background: bg,
      color,
      fontFamily: font,
      fontWeight: font === HEAD ? 800 : 900,
      fontSize: size,
      lineHeight: 1,
      padding: `${size * 0.42}px ${size * 0.75}px ${size * 0.36}px`,
      borderRadius: size * 1.2,
      border: border ? `6px solid ${border}` : undefined,
      boxShadow: "0 10px 0 rgba(15,23,42,0.35)",
      whiteSpace: "nowrap",
      letterSpacing: 1,
    }}
  >
    {children}
  </div>
);

/** Absolutely positioned, horizontally centred row. */
const Row: React.FC<{ y: number; children: React.ReactNode }> = ({ y, children }) => (
  <div style={{ position: "absolute", top: y, left: 0, right: 0, display: "flex", flexDirection: "column", alignItems: "center", gap: 14 }}>{children}</div>
);

const Star: React.FC<{ size: number; color: string }> = ({ size, color }) => (
  <svg width={size} height={size} viewBox="0 0 100 100">
    <path d="M50 0 C54 34 66 46 100 50 C66 54 54 66 50 100 C46 66 34 54 0 50 C34 46 46 34 50 0Z" fill={color} />
  </svg>
);

type ShotProps = {
  src: string;
  audio?: string;
  trim?: number; // seconds trimmed from the start of the clip
  dur: number; // frames
  zoom?: [number, number];
  enter?: "zoom" | "none";
  exit?: "zoom" | "up" | "none";
  children?: React.ReactNode;
};

const Shot: React.FC<ShotProps> = ({ src, audio, trim = 0, dur, zoom = [1, 1.06], enter = "none", exit = "none", children }) => {
  const frame = useCurrentFrame();
  let scale = interpolate(frame, [0, dur], zoom, { ...clamp, easing: Easing.inOut(Easing.sin) });
  let blur = 0;
  let ty = 0;
  if (enter === "zoom") {
    const e = interpolate(frame, [0, 7], [1, 0], { ...clamp, easing: Easing.out(Easing.cubic) });
    scale *= 1 + 0.7 * e;
    blur += 14 * e;
  }
  if (exit === "zoom") {
    const e = interpolate(frame, [dur - 6, dur], [0, 1], { ...clamp, easing: Easing.in(Easing.cubic) });
    scale *= 1 + 1.0 * e;
    blur += 16 * e;
  }
  if (exit === "up") {
    ty = interpolate(frame, [dur - 8, dur], [0, -100], { ...clamp, easing: Easing.in(Easing.cubic) });
  }
  return (
    <AbsoluteFill style={{ transform: `translateY(${ty}%)` }}>
      <AbsoluteFill style={{ transform: `scale(${scale})`, filter: blur > 0.2 ? `blur(${blur}px)` : undefined }}>
        <OffthreadVideo src={staticFile(src)} trimBefore={s(trim)} muted style={{ width: "100%", height: "100%", objectFit: "cover" }} />
      </AbsoluteFill>
      {audio ? <Html5Audio src={staticFile(audio)} /> : null}
      {children}
    </AbsoluteFill>
  );
};

/** Soft gradient so lower-third text always reads. */
const Scrim: React.FC<{ from?: number; top?: boolean; strength?: number }> = ({ from = 0, top = false, strength = 0.55 }) => {
  const frame = useCurrentFrame();
  const o = interpolate(frame, [from, from + 8], [0, 1], clamp);
  return (
    <AbsoluteFill
      style={{
        opacity: o,
        background: top
          ? `linear-gradient(180deg, rgba(15,23,42,${strength}) 0%, rgba(15,23,42,0) 26%)`
          : `linear-gradient(0deg, rgba(15,23,42,${strength}) 0%, rgba(15,23,42,${strength * 0.6}) 22%, rgba(15,23,42,0) 46%)`,
      }}
    />
  );
};

// ---------- scenes ----------
const Scene1: React.FC = () => (
  <Shot src="s1.mp4" audio="s1.wav" trim={0.3} dur={s(7.5)} zoom={[1, 1.1]} exit="zoom">
    <Scrim from={s(5.7)} />
    <Row y={1330}>
      <Pop from={s(0.5)} to={s(2.5)} rotate={-3}>
        <Chip bg={GOLD} color={NAVY} size={72}>
          HEY, PARENTS!
        </Chip>
      </Pop>
    </Row>
    <Row y={1230}>
      <Pop from={s(5.85)}>
        <Txt size={128}>MORE</Txt>
      </Pop>
      <Pop from={s(6.0)} rotate={-2}>
        <Txt size={130} color={GOLD}>
          SCREEN TIME?
        </Txt>
      </Pop>
    </Row>
  </Shot>
);

const Scene2: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const createAt = s(6.04);
  const punch = spring({ frame: frame - createAt, fps, config: { damping: 7, stiffness: 220, mass: 0.6 } });
  return (
    <Shot src="s2.mp4" audio="s2.wav" trim={0.3} dur={s(7.5)} zoom={[1, 1.07]} enter="zoom">
      <Scrim from={s(5.3)} />
      <Row y={1330}>
        <Pop from={s(0.4)} to={s(1.7)} rotate={3}>
          <Chip bg={PINK} size={72}>
            BUT WAIT…
          </Chip>
        </Pop>
      </Row>
      <Row y={1150}>
        <Pop from={s(5.45)}>
          <Txt size={104}>WHAT IF THEY</Txt>
        </Pop>
        {frame >= createAt ? (
          <div style={{ transform: `scale(${0.3 + 0.7 * punch}) rotate(-3deg)`, position: "relative", margin: "4px 0" }}>
            <Txt size={196} color={GOLD} sw={24}>
              CREATED
            </Txt>
            <div style={{ position: "absolute", right: -40, top: -50, transform: `scale(${punch}) rotate(${frame * 3}deg)` }}>
              <Star size={90} color={PINK} />
            </div>
            <div style={{ position: "absolute", left: -46, bottom: -10, transform: `scale(${punch * 0.8}) rotate(${-frame * 3}deg)` }}>
              <Star size={64} color={CREAM} />
            </div>
          </div>
        ) : null}
        <Pop from={s(6.5)}>
          <Txt size={104}>INSTEAD?</Txt>
        </Pop>
      </Row>
    </Shot>
  );
};

const Scene3: React.FC = () => {
  const items: [string, number, number, string, string][] = [
    ["AI IMAGES", 2.0, 3.5, GOLD, NAVY],
    ["AI SONGS", 4.55, 5.25, PINK, CREAM],
    ["AI VIDEOS", 5.3, 6.35, BLUE, CREAM],
    ["WEBSITES", 6.9, 7.8, GOLD, NAVY],
    ["GAMES", 7.85, 9.2, PINK, CREAM],
  ];
  return (
    <Shot src="s3.mp4" audio="s3.wav" dur={s(9)} zoom={[1.06, 1.0]}>
      <Scrim top strength={0.6} />
      <Scrim strength={0.5} />
      <Row y={170}>
        <Pop from={s(0.35)} to={s(6.3)}>
          <Txt size={112}>
            <span style={{ color: GOLD }}>CREATE</span> WITH AI
          </Txt>
        </Pop>
      </Row>
      <Row y={150}>
        <Pop from={s(6.4)}>
          <Txt size={112} color={GOLD}>
            BUILD
          </Txt>
        </Pop>
        <Pop from={s(6.5)}>
          <Txt size={76}>WITH TECHNOLOGY</Txt>
        </Pop>
      </Row>
      {items.map(([label, a, b, bg, fg], i) => (
        <Row y={1400} key={label}>
          <Pop from={s(a)} to={s(b)} rotate={i % 2 ? 2 : -2}>
            <Chip bg={bg} color={fg} size={92} border={NAVY}>
              {label}
            </Chip>
          </Pop>
        </Row>
      ))}
    </Shot>
  );
};

const LOGO_BG = "#FEFEFE";
const Logo: React.FC<{ size?: number }> = ({ size = 190 }) => (
  <div style={{ height: size, borderRadius: size * 0.2, background: LOGO_BG, padding: `${size * 0.1}px ${size * 0.16}px`, boxShadow: "0 12px 0 rgba(15,23,42,0.4)", display: "flex", alignItems: "center", boxSizing: "border-box" }}>
    <Img src={staticFile("logo_full.png")} style={{ height: "100%" }} />
  </div>
);

const Scene4: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const at = s(4.25);
  const sp = spring({ frame: frame - at, fps, config: { damping: 12, stiffness: 140 } });
  const glow = interpolate(frame, [at, at + 10, at + 30], [0, 1, 0], clamp);
  return (
    <Shot src="s4.mp4" audio="s4.wav" dur={s(8)} zoom={[1.0, 1.06]} exit="zoom">
      <Scrim from={s(2.2)} strength={0.62} />
      <Row y={1360}>
        <Pop from={s(2.35)} to={s(4.2)}>
          <Chip bg={CREAM} color={NAVY} size={52}>
            FUTURE BUILDERS CLUB <span style={{ color: BLUE }}>PRESENTS</span>
          </Chip>
        </Pop>
      </Row>
      {frame >= at ? (
        <Row y={1120}>
          <div style={{ position: "relative", transform: `scale(${sp}) rotate(${(1 - sp) * -40}deg)`, marginBottom: 12 }}>
            <div style={{ position: "absolute", inset: -90, borderRadius: "50%", background: `radial-gradient(circle, rgba(250,204,21,${0.85 * glow}) 0%, rgba(250,204,21,0) 65%)` }} />
            <Logo size={200} />
          </div>
          <Pop from={at + 4}>
            <Txt size={104}>
              FBC AI <span style={{ color: GOLD }}>HOLIDAY LAB</span>
            </Txt>
          </Pop>
          <Pop from={s(6.6)} rotate={-2}>
            <Chip bg={PINK} size={70} border={CREAM}>
              COHORT 2.0
            </Chip>
          </Pop>
        </Row>
      ) : null}
    </Shot>
  );
};

const Scene5: React.FC = () => {
  const words: [string, number, number, string][] = [
    ["LEARN", 1.8, 2.42, CREAM],
    ["EXPERIMENT", 2.45, 3.47, GOLD],
    ["BUILD", 3.5, 4.27, CREAM],
    ["CREATE", 4.3, 5.7, GOLD],
  ];
  return (
    <Shot src="s5.mp4" audio="s5.wav" dur={s(8)} zoom={[1.0, 1.05]} enter="zoom" exit="up">
      <Scrim top strength={0.6} />
      <Scrim strength={0.5} />
      <Row y={170}>
        <Pop from={s(0.3)} rotate={-2}>
          <Txt size={170} color={GOLD}>
            3 WEEKS
          </Txt>
        </Pop>
        <Pop from={s(0.5)}>
          <Txt size={84}>OF CREATIVITY</Txt>
        </Pop>
      </Row>
      {words.map(([w, a, b, c], i) => (
        <Row y={1340} key={w}>
          <Pop from={s(a)} to={s(b)} rotate={i % 2 ? 2 : -2}>
            <Txt size={w.length > 7 ? 150 : 190} color={c} sw={22}>
              {w}
            </Txt>
          </Pop>
        </Row>
      ))}
      <Row y={1400}>
        <Pop from={s(5.9)} to={s(7.75)}>
          <Chip bg={BLUE} size={64} border={CREAM}>
            LIVE ON ZOOM
          </Chip>
        </Pop>
      </Row>
    </Shot>
  );
};

const Confetti: React.FC<{ from: number; count?: number }> = ({ from, count = 46 }) => {
  const frame = useCurrentFrame() - from;
  if (frame < 0) return null;
  const cols = [GOLD, PINK, BLUE, CREAM];
  return (
    <AbsoluteFill>
      {new Array(count).fill(0).map((_, i) => {
        const ang = random(`a${i}`) * Math.PI * 2;
        const sp = 16 + random(`s${i}`) * 34;
        const t = frame;
        const x = 540 + Math.cos(ang) * sp * t * (1 / (1 + t * 0.03));
        const y = 960 + Math.sin(ang) * sp * t * (1 / (1 + t * 0.03)) + 0.45 * t * t;
        const size = 16 + random(`z${i}`) * 26;
        const star = i % 3 === 0;
        const o = interpolate(t, [0, 3, 50, 62], [0, 1, 1, 0], clamp);
        return (
          <div key={i} style={{ position: "absolute", left: x, top: y, opacity: o, transform: `rotate(${t * (6 + random(`r${i}`) * 14)}deg)` }}>
            {star ? <Star size={size * 2} color={cols[i % 4]} /> : <div style={{ width: size, height: size * 0.6, background: cols[i % 4], borderRadius: 4 }} />}
          </div>
        );
      })}
    </AbsoluteFill>
  );
};

const Scene6: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const inY = interpolate(frame, [0, 8], [100, 0], { ...clamp, easing: Easing.out(Easing.cubic) });
  const hit = 68; // "I MADE THIS!" lands on the beat at 42.0 s
  const stamp = spring({ frame: frame - 8, fps, config: { damping: 12, stiffness: 200, mass: 0.8 } });
  const leave = interpolate(frame, [hit - 9, hit - 2], [0, 1], { ...clamp, easing: Easing.in(Easing.cubic) });
  const boom = spring({ frame: frame - hit, fps, config: { damping: 8, stiffness: 200, mass: 0.7 } });
  const flash = frame >= hit ? interpolate(frame, [hit, hit + 8], [0.8, 0], clamp) : 0;
  const bgScale = interpolate(frame, [0, 128], [1.08, 1.2]);
  const rays = frame >= hit ? interpolate(frame, [hit, hit + 14], [0, 1], clamp) : 0;
  return (
    <AbsoluteFill style={{ transform: `translateY(${inY}%)`, background: NAVY }}>
      <AbsoluteFill style={{ transform: `scale(${bgScale})` }}>
        <OffthreadVideo src={staticFile("s6bg.mp4")} muted style={{ width: "100%", height: "100%", objectFit: "cover" }} />
      </AbsoluteFill>
      <AbsoluteFill style={{ background: "rgba(15,23,42,0.74)" }} />
      <AbsoluteFill style={{ background: `radial-gradient(circle at 50% 48%, rgba(37,99,235,0.55) 0%, rgba(37,99,235,0) 55%)` }} />
      {rays > 0 ? (
        <AbsoluteFill style={{ alignItems: "center", justifyContent: "center", opacity: 0.5 * rays }}>
          <div
            style={{
              width: 2600,
              height: 2600,
              borderRadius: "50%",
              background: `repeating-conic-gradient(from ${frame * 0.6}deg, rgba(250,204,21,0.55) 0deg 8deg, rgba(250,204,21,0) 8deg 24deg)`,
              WebkitMaskImage: "radial-gradient(circle, black 10%, transparent 62%)",
              maskImage: "radial-gradient(circle, black 10%, transparent 62%)",
            }}
          />
        </AbsoluteFill>
      ) : null}

      {/* part 1: DEMO DAY */}
      {frame < hit ? (
        <AbsoluteFill style={{ opacity: 1 - leave, transform: `scale(${1 - 0.25 * leave})` }}>
          <Row y={600}>
            <Pop from={3}>
              <Chip bg={CREAM} color={NAVY} size={58}>
                AND THE BEST PART?
              </Chip>
            </Pop>
          </Row>
          <Row y={760}>
            <div style={{ transform: `scale(${2.4 - 1.4 * stamp}) rotate(-4deg)`, opacity: Math.min(1, stamp * 1.5), display: "flex", flexDirection: "column", alignItems: "center" }}>
              <Txt size={260} color={GOLD} stroke={NAVY} sw={26}>
                DEMO
              </Txt>
              <Txt size={260} color={GOLD} stroke={NAVY} sw={26}>
                DAY
              </Txt>
            </div>
          </Row>
          <Row y={1350}>
            <Pop from={24}>
              <div style={{ fontFamily: BODY, fontWeight: 900, fontSize: 56, color: CREAM, textAlign: "center", lineHeight: 1.2 }}>
                Every child shows their parents
                <br />
                what they created
              </div>
            </Pop>
          </Row>
        </AbsoluteFill>
      ) : null}

      {/* part 2: I MADE THIS! */}
      {frame >= hit ? (
        <>
          <Row y={470}>
            <Pop from={hit + 4}>
              <Chip bg={GOLD} color={NAVY} size={60}>
                DEMO DAY
              </Chip>
            </Pop>
          </Row>
          <Row y={640}>
            <div style={{ transform: `scale(${0.2 + 0.8 * boom}) rotate(-5deg)`, display: "flex", flexDirection: "column", alignItems: "center" }}>
              <Txt size={250} color={CREAM} stroke={PINK} sw={30} shadow={"rgba(250,204,21,0.95)"}>
                I MADE
              </Txt>
              <Txt size={330} color={GOLD} stroke={PINK} sw={34} shadow={"rgba(245,243,231,0.95)"}>
                THIS!
              </Txt>
            </div>
          </Row>
          <Confetti from={hit} />
        </>
      ) : null}
      <AbsoluteFill style={{ background: "white", opacity: flash }} />
    </AbsoluteFill>
  );
};

const Scene7: React.FC = () => (
  <Shot src="s7.mp4" audio="s7.wav" trim={0.3} dur={s(7)} zoom={[1.0, 1.09]}>
    <Scrim from={s(4.0)} strength={0.62} />
    <Row y={1180}>
      <Pop from={s(4.2)}>
        <Txt size={124}>REGISTRATION</Txt>
      </Pop>
      <Pop from={s(4.35)} rotate={-2}>
        <Txt size={170} color={GOLD} sw={22}>
          IS OPEN!
        </Txt>
      </Pop>
      <Pop from={s(5.9)} style={{ marginTop: 18 }}>
        <Chip bg={PINK} size={62} border={CREAM}>
          JOIN THE HOLIDAY LAB
        </Chip>
      </Pop>
    </Row>
  </Shot>
);

const Scene8: React.FC = () => {
  const frame = useCurrentFrame();
  const o = interpolate(frame, [0, 9], [0, 1], clamp);
  return (
    <AbsoluteFill style={{ opacity: o }}>
      <Shot src="s8.mp4" audio="s8.wav" dur={s(6.47)} zoom={[1.14, 1.0]}>
        <Scrim from={s(4.6)} />
        <Row y={1290}>
          <Pop from={s(4.9)}>
            <Txt size={96}>LET’S MAKE THIS</Txt>
          </Pop>
          <Pop from={s(5.3)} rotate={-2}>
            <Txt size={110} color={GOLD}>
              HOLIDAY COUNT!
            </Txt>
          </Pop>
        </Row>
      </Shot>
    </AbsoluteFill>
  );
};

const Rise: React.FC<{ at: number; children: React.ReactNode; style?: React.CSSProperties }> = ({ at, children, style }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const sp = spring({ frame: frame - at, fps, config: { damping: 13, stiffness: 150 } });
  return <div style={{ transform: `translateY(${(1 - sp) * 70}px) scale(${0.9 + 0.1 * sp})`, opacity: Math.min(1, sp * 1.6), ...style }}>{children}</div>;
};

const EndCard: React.FC = () => {
  const frame = useCurrentFrame();
  const y = interpolate(frame, [0, 10], [100, 0], { ...clamp, easing: Easing.out(Easing.cubic) });
  const b = 16; // content starts after the wipe
  const pulse = 1 + 0.035 * Math.sin((frame - 110) / 6) * (frame > 110 ? 1 : 0);
  const info: React.CSSProperties = { fontFamily: BODY, fontWeight: 900, color: CREAM, textAlign: "center", whiteSpace: "nowrap" };
  return (
    <AbsoluteFill style={{ transform: `translateY(${y}%)` }}>
      {/* leading stripes of the wipe */}
      <div style={{ position: "absolute", top: -120, left: 0, right: 0, height: 60, background: PINK }} />
      <div style={{ position: "absolute", top: -60, left: 0, right: 0, height: 60, background: GOLD }} />
      <AbsoluteFill style={{ background: NAVY, overflow: "hidden" }}>
        <AbsoluteFill style={{ background: "radial-gradient(circle at 50% 22%, rgba(37,99,235,0.5) 0%, rgba(37,99,235,0) 55%)" }} />
        {new Array(14).fill(0).map((_, i) => {
          const px = random(`ex${i}`) * 1080;
          const py = random(`ey${i}`) * 1920;
          const tw = 0.5 + 0.5 * Math.sin(frame / 9 + i * 1.7);
          return (
            <div key={i} style={{ position: "absolute", left: px, top: py + Math.sin(frame / 40 + i) * 14, opacity: 0.18 + 0.35 * tw, transform: `rotate(${frame * 0.6 + i * 30}deg)` }}>
              <Star size={22 + random(`es${i}`) * 34} color={[GOLD, PINK, BLUE, CREAM][i % 4]} />
            </div>
          );
        })}
        <div style={{ position: "absolute", top: 150, left: 0, right: 0, display: "flex", flexDirection: "column", alignItems: "center" }}>
          <Rise at={b}>
            <Logo size={190} />
          </Rise>
          <Rise at={b + 6} style={{ marginTop: 44 }}>
            <Txt size={128} sw={0} shadow={"rgba(37,99,235,0.9)"}>
              LESS SCROLLING.
            </Txt>
          </Rise>
          <Rise at={b + 14}>
            <Txt size={128} color={GOLD} sw={0} shadow={"rgba(236,72,153,0.9)"}>
              MORE CREATING.
            </Txt>
          </Rise>
          <Rise at={b + 26} style={{ marginTop: 44 }}>
            <Chip bg={BLUE} size={50}>
              FBC AI HOLIDAY LAB • COHORT 2.0
            </Chip>
          </Rise>
          <Rise at={b + 38} style={{ marginTop: 50 }}>
            <div style={{ ...info, fontSize: 49 }}>21 DECEMBER 2026 – 6 JANUARY 2027</div>
          </Rise>
          <Rise at={b + 50} style={{ marginTop: 36, display: "flex", gap: 22 }}>
            <Chip bg={"rgba(245,243,231,0.1)"} border={CREAM} size={44} font={BODY}>
              AGES 9–18
            </Chip>
            <Chip bg={"rgba(245,243,231,0.1)"} border={CREAM} size={44} font={BODY}>
              LIVE ON ZOOM
            </Chip>
          </Rise>
          <Rise at={b + 60} style={{ marginTop: 26 }}>
            <Chip bg={"rgba(250,204,21,0.12)"} border={GOLD} color={GOLD} size={44} font={BODY}>
              DEMO DAY: 9 JANUARY 2027
            </Chip>
          </Rise>
          <Rise at={b + 74} style={{ marginTop: 56 }}>
            <div style={{ background: CREAM, borderRadius: 44, padding: "30px 60px 20px", textAlign: "center", boxShadow: `0 14px 0 ${BLUE}` }}>
              <div style={{ fontFamily: BODY, fontWeight: 900, fontSize: 42, color: BLUE, letterSpacing: 6 }}>WHATSAPP</div>
              <div style={{ fontFamily: HEAD, fontWeight: 800, fontSize: 118, color: NAVY, lineHeight: 1.05, whiteSpace: "nowrap" }}>0816 872 2876</div>
            </div>
          </Rise>
          <Rise at={b + 90} style={{ marginTop: 58 }}>
            <div style={{ transform: `scale(${pulse})` }}>
              <Chip bg={PINK} size={56}>
                SEND <span style={{ color: GOLD }}>“HOLIDAY LAB”</span> TO REGISTER
              </Chip>
            </div>
          </Rise>
        </div>
      </AbsoluteFill>
    </AbsoluteFill>
  );
};

// ---------- global transition overlays ----------
const Flash: React.FC<{ at: number }> = ({ at }) => {
  const frame = useCurrentFrame();
  const o = interpolate(frame, [at - 1, at, at + 6], [0, 0.85, 0], clamp);
  if (o <= 0) return null;
  return <AbsoluteFill style={{ background: "white", opacity: o }} />;
};

const PanelWipe: React.FC<{ at: number }> = ({ at }) => {
  const frame = useCurrentFrame();
  const cols = [GOLD, PINK, BLUE];
  if (frame < at - 14 || frame > at + 16) return null;
  return (
    <AbsoluteFill>
      {cols.map((c, i) => {
        const x = interpolate(frame, [at - 11 + (i - 1) * 3, at + 11 + (i - 1) * 3], [-175, 175], { ...clamp, easing: Easing.inOut(Easing.cubic) });
        return <div key={c} style={{ position: "absolute", top: "-10%", left: "-25%", width: "150%", height: "120%", background: c, transform: `translateX(${x}%) skewX(-12deg)` }} />;
      })}
    </AbsoluteFill>
  );
};

const Advert: React.FC = () => (
  <AbsoluteFill style={{ background: NAVY }}>
    <Sequence from={T.s1} durationInFrames={s(7.5)}>
      <Scene1 />
    </Sequence>
    <Sequence from={T.s2} durationInFrames={s(7.5)}>
      <Scene2 />
    </Sequence>
    <Sequence from={T.s3} durationInFrames={s(9)}>
      <Scene3 />
    </Sequence>
    <Sequence from={T.s4} durationInFrames={s(8)}>
      <Scene4 />
    </Sequence>
    <Sequence from={T.s5} durationInFrames={s(8)}>
      <Scene5 />
    </Sequence>
    <Sequence from={T.s6} durationInFrames={s(4) + 8}>
      <Scene6 />
    </Sequence>
    <Sequence from={T.s7} durationInFrames={s(7)}>
      <Scene7 />
    </Sequence>
    <Sequence from={T.s8} durationInFrames={s(6.47)}>
      <Scene8 />
    </Sequence>
    <Sequence from={T.end} durationInFrames={T.total - T.end}>
      <EndCard />
    </Sequence>
    <Flash at={T.s3} />
    <PanelWipe at={T.s4} />
    <Flash at={T.s7} />
    <Html5Audio src={staticFile("bed.wav")} />
  </AbsoluteFill>
);

const Watermark: React.FC = () => (
  <AbsoluteFill>
    <div style={{ position: "absolute", top: 44, left: 36, display: "flex", alignItems: "center", gap: 16, background: "rgba(15,23,42,0.5)", borderRadius: 48, padding: "9px 28px 9px 10px" }}>
      <div style={{ width: 70, height: 70, borderRadius: 35, background: LOGO_BG, display: "flex", alignItems: "center", justifyContent: "center" }}>
        <Img src={staticFile("logo_mark.png")} style={{ width: 54 }} />
      </div>
      <div style={{ fontFamily: BODY, fontWeight: 900, fontSize: 36, color: CREAM, letterSpacing: 1, whiteSpace: "nowrap" }}>0816 872 2876</div>
    </div>
  </AbsoluteFill>
);

export const MyComposition = () => (
  <>
    <Composition id="FBCHolidayLab" component={Advert} durationInFrames={T.total} fps={FPS} width={1080} height={1920} />
    <Composition id="Watermark" component={Watermark} durationInFrames={1} fps={FPS} width={1080} height={1920} />
  </>
);
