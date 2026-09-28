//src/main/ets/pages/PersonaPage.ets
import router from '@ohos.router';
import { PersonaItem } from '../models/DecisionModels';
import {
  getPersonas, createPersona, updatePersona, deletePersona, resetPersona
} from '../services/DecisionService';

@Entry
@Component
struct PersonaPage {
  @State personas: PersonaItem[] = [];
  @State showCreateDialog: boolean = false;
  @State newName: string = '';
  @State newRiskPreference: string = 'neutral';
  @State newCorePrinciple: string = '';
  @State editingPersonaId: number = -1;
  @State editingCorePrinciple: string = '';
  @State showEditDialog: boolean = false;
  @State totalWeight: number = 0;
  @State showEditNameDialog: boolean = false;
  @State editingName: string = '';
  @State showRiskDialog: boolean = false;
  @State riskTargetPersona: PersonaItem | null = null;

  async aboutToAppear() {
    await this.loadPersonas();
  }

  async loadPersonas() {
    this.personas = await getPersonas();
    this.calculateTotalWeight();
  }

  calculateTotalWeight() {
    this.totalWeight = this.personas.reduce((sum, p) => sum + p.weight, 0);
  }

  async handleCreatePersona() {
    if (!this.newName.trim()) return;
    try {
      const result = await createPersona(this.newName.trim(), this.newRiskPreference, this.newCorePrinciple.trim());
      if (result) {
        this.showCreateDialog = false;
        this.newName = '';
        this.newCorePrinciple = '';
        this.newRiskPreference = 'neutral';
        await this.loadPersonas();
      }
    } catch (err) {
      // 捕获后端返回的错误（如重名）
      const message = (err instanceof Error) ? err.message : '创建失败';
      AlertDialog.show({
        title: '警告',
        message: message,
        autoCancel: true,
        primaryButton: { value: '确认', action: () => {} }
      });
    }
  }

  async handleWeightChange(personaId: number, newWeight: number) {
    // 1. 立即更新本地数据
    const updated = this.personas.map(p => {
      if (p.id === personaId) {
        const newP = new PersonaItem();
        newP.id = p.id;
        newP.name = p.name;
        newP.risk_preference = p.risk_preference;
        newP.core_principle = p.core_principle;
        newP.system_prompt = p.system_prompt;
        newP.weight = newWeight;  // 关键：更新权重
        newP.is_preset = p.is_preset;
        newP.created_at = p.created_at;
        return newP;
      }
      return p;
    });
    this.personas = updated;  // 重新赋值整个数组
    this.calculateTotalWeight();

    // 2. 异步保存到后端
    try {
      await updatePersona(personaId, undefined, undefined, newWeight);
    } catch (err) {
      console.error('handleWeightChange error: ' + JSON.stringify(err));
    }
  }

  async handleDeletePersona(personaId: number) {
    AlertDialog.show({
      title: '确认删除',
      message: '确认删除此分身？删除后不可恢复。',
      autoCancel: true,
      alignment: DialogAlignment.Center,
      primaryButton: { value: '取消', action: () => {} },
      secondaryButton: {
        value: '确认删除',
        fontColor: '#e74c3c',
        action: async () => {
          await deletePersona(personaId);
          await this.loadPersonas();
        }
      }
    });
  }

  async handleResetPersona(personaId: number) {
    await resetPersona(personaId);
    await this.loadPersonas();
  }

  openEditDialog(personaId: number, currentPrinciple: string) {
    this.editingPersonaId = personaId;
    this.editingCorePrinciple = currentPrinciple;
    this.showEditDialog = true;
  }

  async handleSaveEdit() {
    if (this.editingPersonaId > 0) {
      await updatePersona(this.editingPersonaId, undefined, this.editingCorePrinciple.trim());
      this.showEditDialog = false;
      await this.loadPersonas();
    }
  }

  openEditNameDialog(personaId: number, currentName: string) {
    this.editingPersonaId = personaId;
    this.editingName = currentName;
    this.showEditNameDialog = true;
  }

  async handleSaveName() {
    if (this.editingPersonaId > 0 && this.editingName.trim()) {
      const result = await updatePersona(this.editingPersonaId, this.editingName.trim(), undefined, undefined);
      if (result) {
        this.showEditNameDialog = false;
        await this.loadPersonas();
      } else {
        // 重名校验失败
        AlertDialog.show({
          title: '警告',
          message: '已经存在同名分身！请换成其他名字',
          autoCancel: true,
          primaryButton: { value: '确认', action: () => {} }
        });
      }
    }
  }

  getRiskLabel(risk: string): string {
    switch (risk) {
      case 'aggressive': return '激进';
      case 'neutral': return '中性';
      case 'conservative': return '保守';
      default: return '自定义';
    }
  }

  // 用自定义对话框替代 AlertDialog
  showRiskEditor(persona: PersonaItem) {
    this.riskTargetPersona = persona;
    this.showRiskDialog = true;
  }

  async changeRisk(persona: PersonaItem, newRisk: string) {
    // 如果从其他类型变成自定义，且没有一句话原则，提示填写
    if (newRisk === 'custom' && !persona.core_principle.trim()) {
      AlertDialog.show({
        title: '提示',
        message: '建议填写一句话原则以细化分身的风险偏好',
        autoCancel: true,
        primaryButton: { value: '确定', action: () => {} }
      });
    }

    // 调用后端更新风险偏好
    await updatePersona(persona.id, undefined, undefined, undefined,newRisk);
    // 后端需要支持修改 risk_preference 字段
    this.showRiskDialog = false;
    await this.loadPersonas();
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

        Text('分身管理')
          .fontSize(20)
          .fontWeight(FontWeight.Bold)
          .layoutWeight(1)
          .textAlign(TextAlign.Center)

        Button() {
          Text('+ 创建')
            .fontSize(15)
            .fontColor('#ffffff')
        }
        .height(36)
        .padding({ left: 12, right: 12 })
        .backgroundColor('#27ae60')
        .borderRadius(18)
        .onClick(() => { const customCount = this.personas.filter(p => !p.is_preset).length;
          if (customCount >= 3) {
            AlertDialog.show({
              title: '已达上限',
              message: '最多创建3个自定义分身',
              autoCancel: true,
              primaryButton: { value: '确定', action: () => {} }
            });
            return;
          }
          this.showCreateDialog = true; })
      }
      .width('100%')
      .padding({ left: 16, right: 16, top: 12, bottom: 8 })
      .backgroundColor('#ffffff')

      Divider().color('#e0e0e0')

      // 分身列表
      Scroll() {
        Column() {
          ForEach(this.personas, (item: PersonaItem) => {
            Column() {
              Row() {
                Column() {
                  Row() {
                    Text(item.name)
                      .fontSize(16)
                      .fontWeight(FontWeight.Medium)
                      .fontColor('#2c3e50')
                      .onClick(() => {
                        if (!item.is_preset) {
                          this.openEditNameDialog(item.id, item.name);
                        }
                      })

                    Text(item.is_preset ? '系统预置' : '用户自定义')
                      .fontSize(10)
                      .fontColor('#ffffff')
                      .backgroundColor(item.is_preset ? '#3498db' : '#27ae60')
                      .borderRadius(4)
                      .padding({
                        left: 6,
                        right: 6,
                        top: 2,
                        bottom: 2
                      })
                      .margin({ left: 8 })

                    // 风险偏好标签（所有分身都显示，自定义分身可点击修改）
                    Text(this.getRiskLabel(item.risk_preference))
                      .fontSize(10).fontColor('#2c3e50')
                      .backgroundColor('#ecf0f1')
                      .borderRadius(4).padding({ left: 6, right: 6, top: 2, bottom: 2 }).margin({ left: 4 })
                      .onClick(() => {
                        if (!item.is_preset) {
                          this.showRiskEditor(item);
                        }
                      })
                  }

                  Text(item.core_principle)
                    .fontSize(13)
                    .fontColor('#7f8c8d')
                    .maxLines(2)
                    .margin({ top: 4 })
                    .onClick(() => {
                      if (!item.is_preset) {
                        this.openEditDialog(item.id, item.core_principle);
                      }
                    })

                  // 权重滑块
                  Row() {
                    Text('权重：' + item.weight.toFixed(2))
                      .fontSize(12)
                      .fontColor('#95a5a6')
                      .margin({ right: 8 })

                    Slider({
                      value: item.weight,
                      min: 0,
                      max: 1.0,
                      step: 0.05,
                      style: SliderStyle.OutSet
                    })
                      .layoutWeight(1)
                      .enabled(true)
                      .onChange((value: number) => {
                        this.handleWeightChange(item.id, value);
                      })
                  }
                  .width('100%')
                  .margin({ top: 8 })
                }
                .layoutWeight(1)

                // 操作按钮
                if (item.is_preset) {
                  // 预置分身：重置按钮
                  Button() {
                    Text('重置')
                      .fontSize(12)
                      .fontColor('#3498db')
                  }
                  .backgroundColor(Color.Transparent)
                  .onClick(() => this.handleResetPersona(item.id))
                }
                else{
                  Button() {
                    Text('删除')
                      .fontSize(12)
                      .fontColor('#e74c3c')
                  }
                  .backgroundColor(Color.Transparent)
                  .onClick(() => this.handleDeletePersona(item.id))
                }
              }
              .width('100%')
              .padding(16)
            }
            .width('100%')
            .backgroundColor('#ffffff')
            .borderRadius(12)
            .margin({ top: 8, left: 12, right: 12 })
          })
        }
      }
        .layoutWeight(1)

      // 底部权重总和显示
      Row() {
        Text('权重总和：' + this.totalWeight.toFixed(2))
          .fontSize(13)
          .fontColor(this.totalWeight > 1.05 ? '#e74c3c' : '#95a5a6')
        Text('（发送决策时自动归一化）')
          .fontSize(11)
          .fontColor('#bdc3c7')
          .margin({ left: 8 })
      }
      .width('100%')
      .padding({ left: 16, right: 16, top: 8, bottom: 12 })
      .backgroundColor('#f5f6fa')

      // 创建分身对话框
      if (this.showCreateDialog) {
        Column() {
          Column() {
            Text('创建新分身')
              .fontSize(16)
              .fontWeight(FontWeight.Bold)
              .margin({ bottom: 12 })

            TextInput({ text: this.newName, placeholder: '分身名称' })
              .width('100%').height(40).fontSize(14)
              .backgroundColor('#f8f9fa').borderRadius(8).padding(8)
              .margin({ bottom: 8 })
              .onChange((value: string) => { this.newName = value; })

            // 风险偏好选择器
            Row() {
              Text('风险偏好：')
                .fontSize(14).fontColor('#2c3e50').margin({ right: 8 })
              Select([{ value: '激进' }, { value: '中性' }, { value: '保守' }, { value: '自定义' }])
                .selected(this.newRiskPreference === 'aggressive' ? 0 :
                  this.newRiskPreference === 'neutral' ? 1 :
                    this.newRiskPreference === 'conservative' ? 2 : 3)
                .onSelect((index: number) => {
                  const options = ['aggressive', 'neutral', 'conservative', 'custom'];
                  this.newRiskPreference = options[index];
                })
            }
            .width('100%')
            .margin({ bottom: 8 })

            TextInput({ text: this.newCorePrinciple, placeholder: '一句话核心原则（可选）' })
              .width('100%').height(40).fontSize(14)
              .backgroundColor('#f8f9fa').borderRadius(8).padding(8)
              .margin({ bottom: 12 })
              .onChange((value: string) => { this.newCorePrinciple = value; })

            Row() {
              Button('取消')
                .backgroundColor('#bdc3c7').fontColor('#ffffff').borderRadius(8)
                .padding({ left: 16, right: 16 })
                .onClick(() => { this.showCreateDialog = false; })
              Button('创建')
                .backgroundColor('#27ae60').fontColor('#ffffff').borderRadius(8)
                .padding({ left: 16, right: 16 }).margin({ left: 12 })
                .enabled(this.newName.trim() !== '')
                .onClick(() => this.handleCreatePersona())
            }
            .width('100%').justifyContent(FlexAlign.SpaceBetween)
          }
          .width('80%').backgroundColor('#ffffff').borderRadius(12).padding(20)
        }
        .width('100%').height('100%').backgroundColor('rgba(0,0,0,0.4)')
        .justifyContent(FlexAlign.Center)
        .position({ x: 0, y: 0 })
        .onClick(() => { this.showCreateDialog = false; })
      }

      // 编辑核心原则对话框
      if (this.showEditDialog) {
        Column() {
          Column() {
            Text('修改核心原则')
              .fontSize(16).fontWeight(FontWeight.Bold).margin({ bottom: 12 })

            TextInput({ text: this.editingCorePrinciple, placeholder: '一句话核心原则' })
              .width('100%').height(40).fontSize(14)
              .backgroundColor('#f8f9fa').borderRadius(8).padding(8)
              .margin({ bottom: 12 })
              .onChange((value: string) => { this.editingCorePrinciple = value; })

            Row() {
              Button('取消')
                .backgroundColor('#bdc3c7').fontColor('#ffffff').borderRadius(8)
                .padding({ left: 16, right: 16 })
                .onClick(() => { this.showEditDialog = false; })
              Button('保存')
                .backgroundColor('#2980b9').fontColor('#ffffff').borderRadius(8)
                .padding({ left: 16, right: 16 }).margin({ left: 12 })
                .onClick(() => this.handleSaveEdit())
            }
            .width('100%').justifyContent(FlexAlign.SpaceBetween)
          }
          .width('80%').backgroundColor('#ffffff').borderRadius(12).padding(20)
        }
        .width('100%').height('100%').backgroundColor('rgba(0,0,0,0.4)')
        .justifyContent(FlexAlign.Center)
        .position({ x: 0, y: 0 })
        .onClick(() => { this.showEditDialog = false; })
      }

      // 编辑名称对话框
      if (this.showEditNameDialog) {
        Column() {
          Column() {
            Text('修改分身名称')
              .fontSize(16).fontWeight(FontWeight.Bold).margin({ bottom: 12 })

            TextInput({ text: this.editingName, placeholder: '分身名称' })
              .width('100%').height(40).fontSize(14)
              .backgroundColor('#f8f9fa').borderRadius(8).padding(8)
              .margin({ bottom: 12 })
              .onChange((value: string) => { this.editingName = value; })

            Row() {
              Button('取消')
                .backgroundColor('#bdc3c7').fontColor('#ffffff').borderRadius(8)
                .padding({ left: 16, right: 16 })
                .onClick(() => { this.showEditNameDialog = false; })
              Button('保存')
                .backgroundColor('#2980b9').fontColor('#ffffff').borderRadius(8)
                .padding({ left: 16, right: 16 }).margin({ left: 12 })
                .enabled(this.editingName.trim() !== '')
                .onClick(() => this.handleSaveName())
            }
            .width('100%').justifyContent(FlexAlign.SpaceBetween)
          }
          .width('80%').backgroundColor('#ffffff').borderRadius(12).padding(20)
        }
        .width('100%').height('100%').backgroundColor('rgba(0,0,0,0.4)')
        .justifyContent(FlexAlign.Center)
        .position({ x: 0, y: 0 })
        .onClick(() => { this.showEditNameDialog = false; })
      }

      // 风险偏好选择对话框
      if (this.showRiskDialog && this.riskTargetPersona) {
        Column() {
          Column() {
            Text('修改风险偏好').fontSize(16).fontWeight(FontWeight.Bold).margin({ bottom: 12 })
            Text(`当前分身：${this.riskTargetPersona.name}`).fontSize(13).fontColor('#7f8c8d').margin({ bottom: 12 })

            Button('激进（机会优先，重注出击）')
              .width('100%').height(44).fontSize(14)
              .backgroundColor(this.riskTargetPersona.risk_preference === 'aggressive' ? '#3498db' : '#ecf0f1')
              .fontColor(this.riskTargetPersona.risk_preference === 'aggressive' ? '#fff' : '#2c3e50')
              .borderRadius(8).margin({ bottom: 8 })
              .onClick(() => this.changeRisk(this.riskTargetPersona!, 'aggressive'))

            Button('中性（严格按凯利公式，不偏不倚）')
              .width('100%').height(44).fontSize(14)
              .backgroundColor(this.riskTargetPersona.risk_preference === 'neutral' ? '#3498db' : '#ecf0f1')
              .fontColor(this.riskTargetPersona.risk_preference === 'neutral' ? '#fff' : '#2c3e50')
              .borderRadius(8).margin({ bottom: 8 })
              .onClick(() => this.changeRisk(this.riskTargetPersona!, 'neutral'))

            Button('保守（安全边际优先，避免清零）')
              .width('100%').height(44).fontSize(14)
              .backgroundColor(this.riskTargetPersona.risk_preference === 'conservative' ? '#3498db' : '#ecf0f1')
              .fontColor(this.riskTargetPersona.risk_preference === 'conservative' ? '#fff' : '#2c3e50')
              .borderRadius(8).margin({ bottom: 8 })
              .onClick(() => this.changeRisk(this.riskTargetPersona!, 'conservative'))

            Button('自定义（自由定义风险偏好）')
              .width('100%').height(44).fontSize(14)
              .backgroundColor(this.riskTargetPersona.risk_preference === 'custom' ? '#3498db' : '#ecf0f1')
              .fontColor(this.riskTargetPersona.risk_preference === 'custom' ? '#fff' : '#2c3e50')
              .borderRadius(8).margin({ bottom: 16 })
              .onClick(() => this.changeRisk(this.riskTargetPersona!, 'custom'))

            Button('取消')
              .width('100%').height(40).fontSize(14)
              .backgroundColor('#bdc3c7').fontColor('#fff').borderRadius(8)
              .onClick(() => { this.showRiskDialog = false; })
          }
          .width('80%').backgroundColor('#ffffff').borderRadius(12).padding(20)
        }
        .width('100%').height('100%').backgroundColor('rgba(0,0,0,0.4)')
        .justifyContent(FlexAlign.Center).position({ x: 0, y: 0 })
        .onClick(() => { this.showRiskDialog = false; })
      }

    } // 根 Column 结束
    .width('100%')
    .height('100%')
    .backgroundColor('#f5f6fa')
  }
}