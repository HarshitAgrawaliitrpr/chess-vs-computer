"""Train the NNUE network with numpy (training-time only; inference is pure
Python in app/engine/nnue.py).

    768 inputs (one-hot piece-square from the side to move's perspective)
      -> H hidden (ReLU) -> 1 output (centipawns, side to move's view)

Loss: Huber (delta 1) on scores scaled by /400 and clipped to +/-3.75, which
tames mate outliers without erasing their sign.  Horizontal-mirror
augmentation (sq ^ 7 for white-perspective features, sq ^ 63 for black) is
free - the mirrored position has the identical label.

Usage (from backend/, needs numpy):
    python scripts/nnue_train.py --data data/nnue --hidden 32 --epochs 20
Writes: app/engine/weights/nnue-<H>-v1.json  (loadable by Nnue.load).
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import chess  # noqa: E402
import numpy as np  # noqa: E402

from app.engine.nnue import _feature_index  # noqa: E402

SCALE = 400.0
CLIP = 3.75
PAD = 768  # zero-row index for padding
MAX_ACTIVE = 40  # >= 30 non-king pieces, promotions included


def load_rows(data_dir: str) -> dict[str, int]:
    """fen -> score, deduplicated across shards."""
    out: dict[str, int] = {}
    for path in sorted(glob.glob(os.path.join(data_dir, "*.jsonl"))):
        with open(path, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    item = json.loads(line)
                except json.JSONDecodeError:
                    continue  # shard still being written; skip the torn line
                out.setdefault(item["fen"], int(item["score"]))
    return out


def featurize(fen: str) -> list[int]:
    """Active feature indices for the side-to-move perspective."""
    board = chess.Board(fen)
    perspective = board.turn
    idx: list[int] = []
    for square, piece in board.piece_map().items():
        if piece.piece_type == chess.KING:
            continue
        idx.append(_feature_index(piece, square, perspective))
        if len(idx) >= MAX_ACTIVE:
            break  # extreme promotion positions; truncation is harmless noise
    return idx


def build_dataset(rows: dict[str, int]) -> tuple[np.ndarray, np.ndarray]:
    n = len(rows)
    x = np.full((n * 2, MAX_ACTIVE), PAD, dtype=np.int32)
    y = np.empty(n * 2, dtype=np.float32)
    for i, (fen, score) in enumerate(rows.items()):
        idx = featurize(fen)
        arr = np.array(idx, dtype=np.int32)
        x[i, : len(idx)] = arr
        y[i] = np.clip(score / SCALE, -CLIP, CLIP)
        # Horizontal mirror: sq ^ 7 (flip files).  This commutes with the
        # black-perspective rank-flip (^(56^7) = ^63 decomposition holds), so
        # EVERY feature row mirrors with the same ^7; the label is unchanged.
        x[n + i, : len(idx)] = arr ^ 7
        y[n + i] = y[i]
    return x, y


class MLP:
    """W1 (769,H) gather-sum + relu + linear head, trained with Adam."""

    def __init__(self, hidden: int, rng: np.random.Generator) -> None:
        self.w1 = rng.normal(0.0, 0.05, size=(PAD + 1, hidden)).astype(np.float32)
        self.b1 = np.zeros(hidden, dtype=np.float32)
        self.w2 = rng.normal(0.0, 0.1, size=hidden).astype(np.float32)
        self.b2 = np.float32(0.0)
        self._m = [np.zeros_like(p) for p in self.params()]
        self._v = [np.zeros_like(p) for p in self.params()]
        self._t = 0

    def params(self) -> list[np.ndarray]:
        return [self.w1, self.b1, self.w2, np.array([self.b2], dtype=np.float32)]

    def forward(self, xb: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        h = self.w1[xb].sum(axis=1) + self.b1  # (B,H)
        h = np.maximum(h, 0.0)
        z = h @ self.w2 + self.b2
        return z, h

    def loss_and_grads(
        self, xb: np.ndarray, yb: np.ndarray
    ) -> tuple[float, list[np.ndarray]]:
        z, h = self.forward(xb)
        diff = z - yb
        huber = np.where(np.abs(diff) <= 1.0, 0.5 * diff**2, np.abs(diff) - 0.5)
        loss = float(huber.mean())
        dz = np.clip(diff, -1.0, 1.0) / len(yb)  # Huber gradient, mean-reduced
        dw2 = h.T @ dz
        db2 = np.float32(dz.sum())
        dh = np.outer(dz, self.w2) * (h > 0.0)
        db1 = dh.sum(axis=0)
        dw1 = np.zeros_like(self.w1)
        np.add.at(dw1, xb.ravel(), np.repeat(dh, xb.shape[1], axis=0))
        dw1[PAD] = 0.0  # padding row must stay an exact no-op (never train it)
        return loss, [dw1, db1, dw2, np.array([db2], dtype=np.float32)]

    def adam(self, grads: list[np.ndarray], lr: float) -> None:
        self._t += 1
        b1, b2, eps = 0.9, 0.999, 1e-8
        for param, grad, m, v in zip(self.params(), grads, self._m, self._v):
            m[:] = b1 * m + (1 - b1) * grad
            v[:] = b2 * v + (1 - b2) * grad**2
            mhat = m / (1 - b1**self._t)
            vhat = v / (1 - b2**self._t)
            param -= lr * mhat / (np.sqrt(vhat) + eps)


def evaluate_holdout(model: MLP, x: np.ndarray, y: np.ndarray) -> tuple[float, float, float]:
    preds = np.empty_like(y)
    for start in range(0, len(y), 4096):
        preds[start : start + 4096] = model.forward(x[start : start + 4096])[0]
    mae = float(np.abs(preds - y).mean() * SCALE)  # back to centipawns
    if preds.std() > 0 and y.std() > 0:
        r = float(np.corrcoef(preds, y)[0, 1])
    else:
        r = 0.0
    mae_loss = float(np.abs(preds - y).mean())
    return mae_loss, mae, r


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", default="data/nnue")
    parser.add_argument("--hidden", type=int, default=32)
    parser.add_argument("--epochs", type=int, default=20)
    parser.add_argument("--batch", type=int, default=256)
    parser.add_argument("--lr", type=float, default=3e-3)
    parser.add_argument("--out", default="", help="output json (default: engine weights dir)")
    args = parser.parse_args()

    rows = load_rows(args.data)
    print(f"loaded {len(rows)} unique positions")
    if len(rows) < 1000:
        sys.exit("not enough data")

    x, y = build_dataset(rows)
    rng = np.random.default_rng(20261011)
    order = rng.permutation(len(y))
    x, y = x[order], y[order]
    val_n = max(1000, len(y) // 50)
    x_val, y_val = x[:val_n], y[:val_n]
    x_tr, y_tr = x[val_n:], y[val_n:]
    print(f"train {len(y_tr)} / val {len(y_val)} (mirror-augmented)")

    model = MLP(args.hidden, rng)
    best = (1e9, None)
    for epoch in range(1, args.epochs + 1):
        started = time.time()
        ep_order = rng.permutation(len(y_tr))
        losses = []
        for start in range(0, len(ep_order), args.batch):
            idx = ep_order[start : start + args.batch]
            loss, grads = model.loss_and_grads(x_tr[idx], y_tr[idx])
            losses.append(loss)
            model.adam(grads, lr=args.lr * max(0.1, 1.0 - epoch / args.epochs))
        val_loss, mae_cp, r = evaluate_holdout(model, x_val, y_val)
        print(
            f"epoch {epoch:2d}  train {np.mean(losses):.4f}  val {val_loss:.4f}  "
            f"val MAE {mae_cp:5.1f}cp  r={r:.3f}  ({time.time() - started:.0f}s)",
            flush=True,
        )
        if val_loss < best[0]:
            best = (
                val_loss,
                {
                    "val_loss": round(val_loss, 5),
                    "val_mae_cp": round(mae_cp, 2),
                    "pearson": round(r, 4),
                },
            )

    out = args.out or os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "app", "engine", "weights", f"nnue-{args.hidden}-v1.json",
    )
    os.makedirs(os.path.dirname(out), exist_ok=True)
    # Bake the training scale INTO the output head: the engine reads the
    # forward() result as centipawns directly (w2,b2 are scaled, w1/b1 not).
    payload = {
        "hidden": args.hidden,
        "w1": [[round(float(v), 6) for v in row] for row in model.w1[:PAD]],
        "b1": [round(float(v), 6) for v in model.b1],
        "w2": [round(float(v) * SCALE, 6) for v in model.w2],
        "b2": round(float(model.b2) * SCALE, 6),
        "meta": {
            "positions": len(rows),
            "samples": int(len(y)),
            "epochs": args.epochs,
            "scale": SCALE,
            "clip": CLIP,
            "trained_at": time.strftime("%Y-%m-%d %H:%M", time.gmtime()),
            **best[1],
        },
    }
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(payload, fh)
    print(f"wrote {out} ({os.path.getsize(out) // 1024} KB)  meta={best[1]}")


if __name__ == "__main__":
    main()
