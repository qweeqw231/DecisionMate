//src/main/ets/entryability/EntryAbility.ets
import UIAbility from '@ohos.app.ability.UIAbility';
import window from '@ohos.window';

export default class EntryAbility extends UIAbility {
  onCreate(want: Record<string, Object>, launchParam: Object) {
    console.log('EntryAbility onCreate');
  }

  onDestroy() {
    console.log('EntryAbility onDestroy');
  }

  onWindowStageCreate(windowStage: window.WindowStage) {
    console.log('EntryAbility onWindowStageCreate');
    windowStage.loadContent('pages/InputPage', (err, data) => {
      if (err.code) {
        console.error('Failed to load content: ' + JSON.stringify(err));
        return;
      }
      console.info('Content loaded: ' + JSON.stringify(data));
    });
  }

  onWindowStageDestroy() {
    console.log('EntryAbility onWindowStageDestroy');
  }

  onForeground() {
    console.log('EntryAbility onForeground');
  }

  onBackground() {
    console.log('EntryAbility onBackground');
  }
}