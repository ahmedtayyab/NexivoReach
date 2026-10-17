import { APP_VERSION } from '../version';

export default function AppVersionMark() {
  return (
    <span className="app-version" title="App version">
      v{APP_VERSION}
    </span>
  );
}
