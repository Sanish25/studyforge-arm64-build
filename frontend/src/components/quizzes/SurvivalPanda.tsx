import { useEffect, useLayoutEffect, useRef, useState } from "react";
import "./survival.css";

type Props = {
  lives: number;
  maxLives: number;
  happy: boolean;
  onFinalLanding: () => void;
};

const PANDA_SPRITE = "/images/survival/pandu-life-sprite.png";

function getFallLevel(lives: number, maxLives: number) {
  return Math.max(0, Math.min(3, maxLives - lives));
}

export default function SurvivalPanda({ lives, maxLives, happy, onFinalLanding }: Props) {
  const level = getFallLevel(lives, maxLives);
  const [landed, setLanded] = useState(false);
  const frame = level === 3 && !landed ? 2 : level;
  const [previousFrame, setPreviousFrame] = useState<number | null>(null);
  const frameRef = useRef(frame);
  const landingReported = useRef(false);
  const landingTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const onFinalLandingRef = useRef(onFinalLanding);

  useEffect(() => { onFinalLandingRef.current = onFinalLanding; }, [onFinalLanding]);

  useEffect(() => {
    landingReported.current = false;
    setLanded(false);
    if (level !== 3) return;

    const reducedMotion = typeof window.matchMedia === "function"
      && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const revealLanding = () => {
      if (landingReported.current) return;
      setLanded(true);
      landingTimer.current = setTimeout(() => {
        landingReported.current = true;
        onFinalLandingRef.current();
      }, reducedMotion ? 120 : 300);
    };

    // The timeout is a fallback for browsers that suppress animationend. The
    // CSS landing animation uses this same 900ms duration.
    if (reducedMotion) revealLanding();
    else landingTimer.current = setTimeout(revealLanding, 900);
    return () => {
      if (landingTimer.current) clearTimeout(landingTimer.current);
    };
  }, [level]);

  useEffect(() => () => {
    if (landingTimer.current) clearTimeout(landingTimer.current);
  }, []);

  useLayoutEffect(() => {
    if (frameRef.current === frame) return;
    const oldFrame = frameRef.current;
    frameRef.current = frame;
    setPreviousFrame(oldFrame);
    const fadeTimer = window.setTimeout(() => setPreviousFrame(null), 240);
    return () => window.clearTimeout(fadeTimer);
  }, [frame]);

  const frameStyle = (frameIndex: number) => ({
    backgroundImage: `url("${PANDA_SPRITE}")`,
    backgroundPositionX: `${frameIndex * (100 / 3)}%`,
  });
  const label = happy
    ? `Pandu celebrates with ${lives} ${lives === 1 ? "life" : "lives"} left`
    : level === 0
      ? `Pandu standing with ${lives} lives left`
      : level === 3
        ? "Pandu falling to the ground after losing the final life"
        : `Pandu has fallen to level ${level} with ${lives} ${lives === 1 ? "life" : "lives"} left`;

  return <div className="survival-panda-track" aria-label="Panda life progress">
    <div
      key={level}
      className={`survival-panda-motion survival-panda-level-${level}${happy ? " survival-panda-happy" : ""}${landed ? " survival-panda-landed" : ""}`}
      role="img"
      aria-label={label}
      data-lives={lives}
      data-fall-level={level}
      data-frame={frame}
      onAnimationEnd={(event) => {
        // The final level has only the landing animation; relying on a specific
        // AnimationEvent.animationName is brittle in browsers and test DOMs.
        // Ignore bubbled frame cross-fade events from the child spans.
        if (event.target !== event.currentTarget || level !== 3 || landingReported.current) return;
        if (landingTimer.current) clearTimeout(landingTimer.current);
        setLanded(true);
        landingTimer.current = setTimeout(() => {
          landingReported.current = true;
          onFinalLandingRef.current();
        }, 300);
      }}
    >
      {previousFrame !== null && <span className={`survival-panda-frame survival-panda-frame-${previousFrame} survival-panda-frame-leaving`} style={frameStyle(previousFrame)} aria-hidden="true" />}
      <span className={`survival-panda-frame survival-panda-frame-${frame} survival-panda-frame-current${previousFrame !== null ? " survival-panda-frame-entering" : ""}`} style={frameStyle(frame)} aria-hidden="true" />
    </div>
    <div className="survival-panda-ground" aria-hidden="true" />
  </div>;
}
