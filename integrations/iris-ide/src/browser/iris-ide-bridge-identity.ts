/**
 * 브리지 포트·토큰 해결 — 프런트엔드 기여자와 폴러가 공유한다.
 *
 * Theia 내부 내비게이션(폴더 열기·워크스페이스 전환)은 URL 쿼리스트링을 버리므로,
 * 쿼리만 읽으면 재로드 이후 포트가 0이 되어 편집기 상태 전송과 명령 폴링이 함께 멈춘다.
 *
 * ponytail: sessionStorage는 page-session 범위다. 쿼리 없이 새로 열린 탭/창에는 여전히
 * 값이 없다. 상위 해법은 Theia node 백엔드가 이미 가진 IRIS_IDE_BRIDGE_PORT /
 * IRIS_IDE_BRIDGE_TOKEN 환경변수를 프런트엔드로 주입하는 것.
 */

/** 번들 마커 겸 저장 키 — 문자열 리터럴이라 minify에도 남는다. */
const PORT_KEY = 'iris.ide.bridge.port';
const TOKEN_KEY = 'iris.ide.bridge.token';
const CONTROL_PORT_KEY = 'iris.ide.control.port';
const CONTROL_TOKEN_KEY = 'iris.ide.control.token';

export interface IrisIdeBridgeIdentity {
    port: number;
    token: string;
}

export interface IrisIdeControlIdentity {
    port: number;
    token: string;
}

function store(): Storage | undefined {
    try {
        return window.sessionStorage;
    } catch {
        return undefined; /* ponytail: private mode / sandbox may block storage */
    }
}

function resolveStoredIdentity(
    queryPort: string,
    queryToken: string,
    portKey: string,
    tokenKey: string,
): IrisIdeBridgeIdentity {
    const params = new URLSearchParams(window.location.search);
    const port = parseInt(params.get(queryPort) || '0', 10) || 0;
    const token = params.get(queryToken) || '';
    if (port && token) {
        try {
            store()?.setItem(portKey, String(port));
            store()?.setItem(tokenKey, token);
        } catch {
            /* ponytail: storage quota / private mode */
        }
        return { port, token };
    }
    try {
        const saved = store();
        return {
            port: parseInt(saved?.getItem(portKey) || '0', 10) || 0,
            token: saved?.getItem(tokenKey) || '',
        };
    } catch {
        return { port: 0, token: '' };
    }
}

/**
 * 쿼리파라미터가 있으면 그것을 쓰고 저장한다 — 토큰은 IDE 기동마다 회전하므로 항상 덮어쓴다.
 * 없으면 같은 page-session에 저장된 값으로 대체한다.
 */
export function resolveBridgeIdentity(): IrisIdeBridgeIdentity {
    return resolveStoredIdentity('iris_bridge_port', 'iris_bridge_token', PORT_KEY, TOKEN_KEY);
}

/** Control Surface 신원 — askIris / companion DnD 우회에 사용. 쿼리 소실 시에도 승계. */
export function resolveControlIdentity(): IrisIdeControlIdentity {
    return resolveStoredIdentity('iris_control_port', 'iris_control_token', CONTROL_PORT_KEY, CONTROL_TOKEN_KEY);
}
