//src/main/ets/pages/SettingsPage.ets
import router from '@ohos.router';
import preferences from '@ohos.data.preferences';
import { Constants } from '../common/Constants';
import { clearAllConversations } from '../services/DecisionService';

@Entry
@Component
struct SettingsPage {
  @State serverUrl: string = '';
  @State saveMessage: string = '';

  async aboutToAppear() {
    this.serverUrl = await Constants.getBaseUrl();
  }

  build() {
    Column() {
      // 顶部导航栏
      Row() {
        Button() {
          Text('← 返回')
            .fontSize(15)
            .fontColor('#3498db')
        }
        .backgroundColor(Color.Transparent)
        .onClick(() => router.back())

        Text('设置')
          .fontSize(20)
          .fontWeight(FontWeight.Bold)
          .layoutWeight(1)
          .textAlign(TextAlign.Center)

        Button() {
          Text('保存')
            .fontSize(15)
            .fontColor('#ffffff')
        }
        .height(36)
        .padding({ left: 16, right: 16 })
        .backgroundColor('#27ae60')
        .borderRadius(18)
        .onClick(() => this.saveSettings())
      }
      .width('100%')
      .padding({ left: 16, right: 16, top: 16, bottom: 10 })

      // 设置内容
      Column() {
        Text('后端服务地址')
          .fontSize(16)
          .fontWeight(FontWeight.Medium)
          .margin({ top: 20, bottom: 8 })

        Text('请输入电脑的IP地址和端口，例如：http://192.168.1.100:8000')
          .fontSize(12)
          .fontColor('#999999')
          .margin({ bottom: 12 })

        TextInput({ text: this.serverUrl })
          .width('100%')
          .height(48)
          .fontSize(15)
          .backgroundColor('#f8f9fa')
          .borderRadius(8)
          .padding(12)
          .onChange((value: string) => {
            this.serverUrl = value;
          })

        if (this.saveMessage) {
          Text(this.saveMessage)
            .fontSize(14)
            .fontColor('#27ae60')
            .margin({ top: 16 })
        }
      }
      .width('100%')
      .padding({ left: 16, right: 16 })

      // 分身管理入口
      Column() {
        Text('决策分身')
          .fontSize(16)
          .fontWeight(FontWeight.Medium)
          .margin({ top: 20, bottom: 12 })

        Button('分身管理')
          .width('100%')
          .height(48)
          .fontSize(15)
          .backgroundColor('#3498db')
          .fontColor('#ffffff')
          .borderRadius(12)
          .onClick(() => {
            router.pushUrl({ url: 'pages/PersonaPage' });
          })
      }
      .width('100%')
      .padding({ left: 16, right: 16 })

      // 清空所有对话
      Column() {
        Text('数据管理')
          .fontSize(16)
          .fontWeight(FontWeight.Medium)
          .margin({ top: 30, bottom: 12 })

        Button('清空所有对话')
          .width('100%')
          .height(48)
          .fontSize(15)
          .backgroundColor('#e74c3c')
          .fontColor('#ffffff')
          .borderRadius(12)
          .onClick(async () => {
            // 确认对话框
            AlertDialog.show({
              title: '确认清空',
              message: '确认删除所有对话？删除后内容无法恢复。',
              autoCancel: true,
              alignment: DialogAlignment.Center,
              primaryButton: {
                value: '取消',
                action: () => { }
              },
              secondaryButton: {
                value: '确认删除',
                fontColor: '#e74c3c',
                action: async () => {
                  const result = await clearAllConversations();
                  if (result) {
                    AlertDialog.show({
                      title: '已清空',
                      message: '所有对话已删除。',
                      autoCancel: true,
                      alignment: DialogAlignment.Center,
                      primaryButton: {
                        value: '确定',
                        action: () => { }
                      }
                    });
                  }
                }
              }
            });
          })
      }
      .width('100%')
      .padding({ left: 16, right: 16 })
    }
    .width('100%')
    .height('100%')
    .backgroundColor('#f5f6fa')
  }

  async saveSettings() {
    try {
      const prefs = await preferences.getPreferences(getContext(), Constants.PREF_NAME);
      await prefs.put('base_url', this.serverUrl);
      await prefs.flush();
      this.saveMessage = '已保存，下次请求生效';
    } catch (err) {
      this.saveMessage = '保存失败，请重试';
    }
  }
}