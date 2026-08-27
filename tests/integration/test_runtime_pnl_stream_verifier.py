import asyncio
import json
import logging
import sys
from pathlib import Path
from typing import Any, Dict, List
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import websockets  # noqa: E402

from main import TradingSystem  # noqa: E402
from web_interface.server import TargetArchitectureUIServer, UIWebSocketHub  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("pnl_verifier")


async def run_live_verification(total_ticks_target: int = 120):
    logger.info("=== [START] 실제 런타임 UI PnL 데이터 공급 경로 E2E 검증 ===")
    
    # 1. TradingSystem 인스턴스 생성 및 초기화
    config = {"broker_mode": "PAPER", "initial_capital": 50_000_000.0}
    system = TradingSystem(config)
    await system.initialize()
    
    # 2. WebSocket 서버 기동 (포트 8765)
    await system.ui_ws.start()
    logger.info("UI WebSocket 서버 기동 완료 (ws://127.0.0.1:8765)")
    
    received_packets: List[Dict[str, Any]] = []
    rx_event = asyncio.Event()
    stop_client = asyncio.Event()

    async def ws_client_worker():
        uri = "ws://127.0.0.1:8765"
        async with websockets.connect(uri) as ws:
            logger.info("WebSocket 클라이언트 연결 성공")
            # 1번째 메시지는 초기 스냅샷
            initial_msg = await ws.recv()
            initial_data = json.loads(initial_msg)
            received_packets.append(initial_data)
            rx_event.set()
            
            while not stop_client.is_set():
                try:
                    msg = await asyncio.wait_for(ws.recv(), timeout=1.0)
                    data = json.loads(msg)
                    received_packets.append(data)
                except asyncio.TimeoutError:
                    if stop_client.is_set():
                        break
                except Exception as exc:
                    logger.warning("Client recv exception: %s", exc)
                    break

    client_task = asyncio.create_task(ws_client_worker())
    await rx_event.wait()
    logger.info("초기 스냅샷 수신 확인: type=%s", received_packets[0].get("type"))
    
    # 3. 실제 시뮬레이션 틱 스트림 실행
    logger.info("TradingSystem.run_loop(%d 틱) 실행 시작", total_ticks_target)
    await system.run_loop(max_ticks=total_ticks_target)
    logger.info("TradingSystem.run_loop 실행 완료. 처리된 틱 수: %d", system.ticks_processed)
    
    # 수신 대기 및 클라이언트 종료
    await asyncio.sleep(0.3)
    stop_client.set()
    await client_task
    await system.ui_ws.stop()
    await system.shutdown()
    
    # 4. 실측 데이터 정밀 대조 및 계측
    # 첫 패킷은 초기 스냅샷이므로 틱 broadcast 패킷은 1번 인덱스부터
    broadcast_packets = received_packets[1:]
    
    total_ticks = system.ticks_processed
    total_broadcasts = len(broadcast_packets)
    
    seq_ids = []
    coord_x_list = []
    coord_y_list = []
    pnl_total_list = []
    mismatch_coord_seq = []
    mismatch_coord_pnl = []
    
    # Zustand rootStore 시뮬레이션
    simulated_root_coords = []
    
    for idx, pkt in enumerate(broadcast_packets):
        market = pkt.get("market", {})
        seq_id = market.get("seq_id")
        coord = pkt.get("coord", {})
        pnl = pkt.get("pnl", {})
        
        seq_ids.append(seq_id)
        cx = coord.get("x")
        cy = coord.get("y")
        coord_x_list.append(cx)
        coord_y_list.append(cy)
        pnl_total_list.append(pnl.get("total"))
        
        # rootStore.updateData 시뮬레이션: incoming.coord 누적
        if coord:
            simulated_root_coords.append(coord)
            if len(simulated_root_coords) > 1000:
                simulated_root_coords = simulated_root_coords[-1000:]
        
        # 검증: coord.x === seq_id
        if cx != seq_id:
            mismatch_coord_seq.append((idx, seq_id, cx))
            
        # 검증: coord.y === pnl.total
        if cy != pnl.get("total"):
            mismatch_coord_pnl.append((idx, pnl.get("total"), cy))

    first_seq_id = seq_ids[0] if seq_ids else None
    last_seq_id = seq_ids[-1] if seq_ids else None
    
    # 누락 및 중복 seq_id 검사
    expected_seqs = list(range(first_seq_id, last_seq_id + 1)) if first_seq_id is not None and last_seq_id is not None else []
    missing_seqs = [s for s in expected_seqs if s not in seq_ids]
    duplicate_seqs = [s for s in seq_ids if seq_ids.count(s) > 1]
    duplicate_seqs = list(set(duplicate_seqs))
    
    logger.info("=== [결과 집계] ===")
    logger.info("총 Tick 수: %d", total_ticks)
    logger.info("총 Broadcast 수: %d", total_broadcasts)
    logger.info("Broadcast / Tick 비율: %.4f", total_broadcasts / total_ticks if total_ticks else 0)
    logger.info("첫 seq_id: %s, 마지막 seq_id: %s", first_seq_id, last_seq_id)
    logger.info("누락 seq_id 수: %d, 중복 seq_id 수: %d", len(missing_seqs), len(duplicate_seqs))
    logger.info("coord.x ↔ seq_id 불일치 건수: %d", len(mismatch_coord_seq))
    logger.info("coord.y ↔ pnl.total 불일치 건수: %d", len(mismatch_coord_pnl))
    logger.info("rootStore.coords 최종 개수: %d (마지막 좌표: %s)", len(simulated_root_coords), simulated_root_coords[-1] if simulated_root_coords else None)
    
    results = {
        "total_ticks": total_ticks,
        "total_broadcasts": total_broadcasts,
        "ratio": total_broadcasts / total_ticks if total_ticks else 0,
        "first_seq_id": first_seq_id,
        "last_seq_id": last_seq_id,
        "missing_seqs": missing_seqs,
        "duplicate_seqs": duplicate_seqs,
        "mismatch_coord_seq_count": len(mismatch_coord_seq),
        "mismatch_coord_pnl_count": len(mismatch_coord_pnl),
        "root_coords_count": len(simulated_root_coords),
        "sample_points": [
            {
                "tick_seq": seq_ids[i],
                "coord_x": coord_x_list[i],
                "coord_y": coord_y_list[i],
                "pnl_total": pnl_total_list[i],
                "root_coord": simulated_root_coords[i],
            }
            for i in range(0, min(5, len(seq_ids)))
        ]
    }
    
    print("\n--- JSON_RESULT_START ---")
    print(json.dumps(results, indent=2, ensure_ascii=False))
    print("--- JSON_RESULT_END ---\n")
    
    assert total_ticks >= 100, f"Tick count {total_ticks} < 100"
    assert total_broadcasts == total_ticks, f"Broadcast count {total_broadcasts} != {total_ticks}"
    assert len(missing_seqs) == 0, f"Missing seqs: {missing_seqs}"
    assert len(duplicate_seqs) == 0, f"Duplicate seqs: {duplicate_seqs}"
    assert len(mismatch_coord_seq) == 0, f"Coord seq mismatch: {mismatch_coord_seq}"
    assert len(mismatch_coord_pnl) == 0, f"Coord pnl mismatch: {mismatch_coord_pnl}"
    assert len(simulated_root_coords) == total_ticks, f"Root coords length {len(simulated_root_coords)} != {total_ticks}"
    logger.info("=== [전수 PASS] 런타임 E2E 데이터 공급 경로 무결성 검증 완료 ===")


if __name__ == "__main__":
    asyncio.run(run_live_verification(120))
