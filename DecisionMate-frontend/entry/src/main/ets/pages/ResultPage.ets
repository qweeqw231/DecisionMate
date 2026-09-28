//src/main/ets/pages/ResultPage.ets
import router from '@ohos.router';
import { DecisionReport, PersonaResult, StrategyItem } from '../models/DecisionModels';
import pasteboard from '@ohos.pasteboard';
import { submitFeedback } from '../services/DecisionService'

@Entry
@Component
struct ResultPage {
  @State report: DecisionReport | null = null;
  @State copyButtonText: string = '复制全文';
  @State expandAllPersonas: boolean = false; // 控制一键展开/折叠
  @State showPersonaFeedbackDialog: boolean = false;
  @State personaFeedbackTarget: PersonaResult | null = null;
  @State personaFeedbackType: string = '';
  @State personaFeedbackText: string = '';
  @State convId: number = -1;
  @State msgId: number = -1;

  aboutToAppear() {
    const params: Record<string, Object> = router.getParams() as Record<string, Object>;
    if (params && params['report']) {
      this.report = params['report'] as DecisionReport;
    }
    if (params && params['convId']) {
      this.convId = params['convId'] as number;
    }
    if (params && params['msgId']) {
      this.msgId = params['msgId'] as number;
    }
  }

  openPersonaFeedback(pr: PersonaResult) {
    this.personaFeedbackTarget = pr;
    this.personaFeedbackType = '';
    this.personaFeedbackText = '';
    this.showPersonaFeedbackDialog = true;
  }

  async submitPersonaFeedback() {
    if (!this.personaFeedbackType || !this.personaFeedbackTarget) return;

    try {
      const response = await submitFeedback(
        // 注意：这里需要传入 conv_id 和 msg_id，但 ResultPage 目前没有这些参数
        // 暂时使用集群级反馈接口，在 feedback_text 中附加分身名称作为标识
        this.convId,                                    // conv_id
        this.msgId,                                     // msg_id
        this.personaFeedbackType,                       // feedback_type
        `[分身: ${this.personaFeedbackTarget.name}] ${this.personaFeedbackText || ''}`
      );
      this.showPersonaFeedbackDialog = false;
    } catch (err) {
      console.error('submitPersonaFeedback error: ' + JSON.stringify(err));
    }
  }

  build() {
    Column() {
      // 顶部导航栏
      Row() {
        Button() {
          Text('返回')
            .fontSize(15).fontColor('#3498db')
        }
        .backgroundColor(Color.Transparent)
        .onClick(() => router.back())

        Text('分析结果')
          .fontSize(20).fontWeight(FontWeight.Bold).fontColor('#1a1a1a')
          .layoutWeight(1).textAlign(TextAlign.Center)

        // 一键复制全文按钮（始终保留）
        Button() {
          Text(this.copyButtonText).fontSize(14).fontColor('#ffffff')
        }
        .height(36).padding({ left: 12, right: 12 })
        .backgroundColor('#27ae60').borderRadius(18)
        .onClick(() => this.copyReportToClipboard())
      }
      .width('100%').padding({ left: 16, right: 16, top: 16, bottom: 10 }).backgroundColor('#ffffff')

      if (this.report) {
        Scroll() {
          Column() {
            // ========== 会商摘要卡片（多分身模式） ==========
            if (this.report.persona_results && this.report.persona_results.length > 0) {
              // 投票概览
              Column() {
                Text('综合建议')
                  .fontSize(14).fontColor('#ffffff').opacity(0.8).margin({ bottom: 8 })
                Text(this.report.recommendation)
                  .fontSize(16).fontWeight(FontWeight.Medium).fontColor('#ffffff').lineHeight(24)

                // 冲突标签
                if (this.report.conflict_detected) {
                  Text('⚠️ 分身意见分歧：不同分身的建议存在显著差异，请仔细审阅各分身独立意见后再做决定。')
                    .fontSize(12).fontColor('#f39c12').margin({ top: 8 }).maxLines(3)
                }

                // 各分身投票概览
                Text('')
                  .margin({ top: 12 })
                ForEach(this.report.persona_results, (pr: PersonaResult) => {
                  Text(`${pr.name}（权重：${pr.weight.toFixed(2)}）f*=${(pr.f_star * 100).toFixed(1)}% ✓`)
                    .fontSize(13).fontColor('#ecf0f1').margin({ top: 2 })
                })
              }
              .width('100%').backgroundColor('#2c3e50').borderRadius(12).padding(20).margin({ top: 16 })

              // 关键指标
              Row() {
                Column() {
                  Text('最优下注比例').fontSize(11).fontColor('#7f8c8d').margin({ bottom: 4 })
                  Text((this.report.f_star * 100).toFixed(1) + '%')
                    .fontSize(28).fontWeight(FontWeight.Bold)
                    .fontColor(this.report.f_star > 0.5 ? '#27ae60' : this.report.f_star >= 0 ? '#f39c12' : '#e74c3c')
                }
                .layoutWeight(1).alignItems(HorizontalAlign.Center)

                Divider().vertical(true).height(40).color('#e0e0e0').margin({ left: 12, right: 12 })

                Column() {
                  Text('风险等级').fontSize(11).fontColor('#7f8c8d').margin({ bottom: 4 })
                  Text(this.report.risk_level)
                    .fontSize(24).fontWeight(FontWeight.Bold)
                    .fontColor(this.report.risk_level === '高' ? '#e74c3c' : this.report.risk_level === '中' ? '#f39c12' : '#27ae60')
                }
                .layoutWeight(1).alignItems(HorizontalAlign.Center)

                Divider().vertical(true).height(40).color('#e0e0e0').margin({ left: 12, right: 12 })

                Column() {
                  Text('场景类型').fontSize(11).fontColor('#7f8c8d').margin({ bottom: 4 })
                  Text(this.report.scenario_type)
                    .fontSize(13).fontWeight(FontWeight.Medium).fontColor('#2c3e50').maxLines(2).textAlign(TextAlign.Center)
                }
                .layoutWeight(1).alignItems(HorizontalAlign.Center)
              }
              .width('100%').backgroundColor('#ffffff').borderRadius(12).padding(20).margin({ top: 12 })
              .shadow({ radius: 4, color: '#00000010', offsetX: 0, offsetY: 2 })

              // 一键展开/折叠按钮
              Row() {
                Button('展开全部').fontSize(12).backgroundColor('#3498db').fontColor('#fff').borderRadius(8).padding({ left: 12, right: 12 })
                  .onClick(() => this.expandAllPersonas = true)
                Button('折叠全部').fontSize(12).backgroundColor('#95a5a6').fontColor('#fff').borderRadius(8).padding({ left: 12, right: 12 }).margin({ left: 8 })
                  .onClick(() => this.expandAllPersonas = false)
              }
              .width('100%').justifyContent(FlexAlign.End).margin({ top: 12 })

              // 各分身详情
              ForEach(this.report.persona_results, (pr: PersonaResult) => {
                this.PersonaCard(pr)
              })

              // 量化分析、风险评估、计算过程（使用会商摘要数据）
              this.buildCard('量化分析', this.report.quant_opinion, '#eaf2f8')
              this.buildCard('风险评估', this.report.risk_opinion, '#fef9e7')
              this.buildCard('计算过程', this.report.calculation_detail, '#f4f6f7')
            } else {
              // ========== 单分身模式（保持原样） ==========
              Column() {
                Text('综合建议').fontSize(14).fontColor('#ffffff').opacity(0.8).margin({ bottom: 8 })
                Text(this.report.recommendation).fontSize(16).fontWeight(FontWeight.Medium).fontColor('#ffffff').lineHeight(24)
              }
              .width('100%').backgroundColor('#2c3e50').borderRadius(12).padding(20).margin({ top: 16 })

              Row() {
                Column() {
                  Text('最优下注比例').fontSize(11).fontColor('#7f8c8d').margin({ bottom: 4 })
                  Text((this.report.f_star * 100).toFixed(1) + '%')
                    .fontSize(28).fontWeight(FontWeight.Bold)
                    .fontColor(this.report.f_star > 0.5 ? '#27ae60' : this.report.f_star >= 0 ? '#f39c12' : '#e74c3c')
                }
                .layoutWeight(1).alignItems(HorizontalAlign.Center)

                Divider().vertical(true).height(40).color('#e0e0e0').margin({ left: 12, right: 12 })

                Column() {
                  Text('风险等级').fontSize(11).fontColor('#7f8c8d').margin({ bottom: 4 })
                  Text(this.report.risk_level)
                    .fontSize(24).fontWeight(FontWeight.Bold)
                    .fontColor(this.report.risk_level === '高' ? '#e74c3c' : this.report.risk_level === '中' ? '#f39c12' : '#27ae60')
                }
                .layoutWeight(1).alignItems(HorizontalAlign.Center)

                Divider().vertical(true).height(40).color('#e0e0e0').margin({ left: 12, right: 12 })

                Column() {
                  Text('场景类型').fontSize(11).fontColor('#7f8c8d').margin({ bottom: 4 })
                  Text(this.report.scenario_type)
                    .fontSize(13).fontWeight(FontWeight.Medium).fontColor('#2c3e50').maxLines(2).textAlign(TextAlign.Center)
                }
                .layoutWeight(1).alignItems(HorizontalAlign.Center)
              }
              .width('100%').backgroundColor('#ffffff').borderRadius(12).padding(20).margin({ top: 12 })
              .shadow({ radius: 4, color: '#00000010', offsetX: 0, offsetY: 2 })

              this.buildCard('量化分析', this.report.quant_opinion, '#eaf2f8')
              this.buildCard('风险评估', this.report.risk_opinion, '#fef9e7')
              this.buildCard('计算过程', this.report.calculation_detail, '#f4f6f7')
            }

            // ========== 场景策略（Phase 2 新增）（单分身和多分身都保留）  ==========
            if (this.report.scene_result && this.report.scene_result.scene_recognized) {
              Column() {
                Text('📅 分阶段策略').fontSize(14).fontWeight(FontWeight.Medium).fontColor('#2c3e50').margin({ bottom: 8 })
                Text(this.report.scene_result.timeline_summary).fontSize(12).fontColor('#7f8c8d').margin({ bottom: 16 }).lineHeight(20)
                ForEach(this.report.scene_result.strategies, (item: StrategyItem, index: number) => {
                  Column() {
                    Row() {
                      Text(`${index + 1}. ${item.strategy_name}`).fontSize(14).fontWeight(FontWeight.Medium).fontColor('#2c3e50').layoutWeight(1)
                      Text(item.date_range).fontSize(11).fontColor('#95a5a6')
                    }.width('100%').margin({ bottom: 6 })
                    Text(item.suggestion).fontSize(13).fontColor('#555555').lineHeight(20).margin({ bottom: 4 })
                    Text(`📌 ${item.reference}`).fontSize(11).fontColor('#95a5a6').fontStyle(FontStyle.Italic)
                  }
                  .width('100%').backgroundColor('#f0f8f0').borderRadius(8).padding(14).margin({ top: index > 0 ? 10 : 0 })
                })
              }
              .width('100%').backgroundColor('#e8f5e9').borderRadius(12).padding(16).margin({ top: 12 })
            }

            // 分身级反馈对话框
            if (this.showPersonaFeedbackDialog && this.personaFeedbackTarget) {
              Column() {
                Column() {
                  Text(`对“${this.personaFeedbackTarget.name}”的反馈`)
                    .fontSize(16).fontWeight(FontWeight.Bold).margin({ bottom: 12 })

                  Row() {
                    Button('有用 ✓')
                      .backgroundColor(this.personaFeedbackType === 'useful' ? '#27ae60' : '#ecf0f1')
                      .fontColor(this.personaFeedbackType === 'useful' ? '#fff' : '#555')
                      .borderRadius(8).padding({ left: 12, right: 12 })
                      .onClick(() => { this.personaFeedbackType = 'useful'; })

                    Button('不太准 ✗')
                      .backgroundColor(this.personaFeedbackType === 'inaccurate' ? '#e74c3c' : '#ecf0f1')
                      .fontColor(this.personaFeedbackType === 'inaccurate' ? '#fff' : '#555')
                      .borderRadius(8).padding({ left: 12, right: 12 }).margin({ left: 12 })
                      .onClick(() => { this.personaFeedbackType = 'inaccurate'; })
                  }
                  .margin({ bottom: 12 })

                  TextInput({ text: this.personaFeedbackText, placeholder: '补充说明（可选）' })
                    .width('100%').height(40).fontSize(14)
                    .backgroundColor('#f8f9fa').borderRadius(8).padding(8)
                    .onChange((value: string) => { this.personaFeedbackText = value; })

                  Row() {
                    Button('取消')
                      .backgroundColor('#bdc3c7').fontColor('#fff').borderRadius(8)
                      .padding({ left: 16, right: 16 })
                      .onClick(() => { this.showPersonaFeedbackDialog = false; })
                    Button('提交')
                      .backgroundColor('#2980b9').fontColor('#fff').borderRadius(8)
                      .padding({ left: 16, right: 16 }).margin({ left: 12 })
                      .enabled(this.personaFeedbackType !== '')
                      .onClick(() => this.submitPersonaFeedback())
                  }
                  .width('100%').justifyContent(FlexAlign.SpaceBetween).margin({ top: 12 })
                }
                .width('80%').backgroundColor('#ffffff').borderRadius(12).padding(20)
              }
              .width('100%').height('100%').backgroundColor('rgba(0,0,0,0.4)')
              .justifyContent(FlexAlign.Center).position({ x: 0, y: 0 })
              .onClick(() => { this.showPersonaFeedbackDialog = false; })
            }

            Text('以上分析仅供参考，最终决策权在你手中')
              .fontSize(12).fontColor('#bdc3c7').margin({ top: 20, bottom: 40 }).textAlign(TextAlign.Center).width('100%')
          }
          .width('100%').padding({ left: 16, right: 16 })
        }
        .layoutWeight(1).scrollable(ScrollDirection.Vertical).scrollBar(BarState.Off)
      } else {
        Column() {
          Text('暂无分析结果').fontSize(16).fontColor('#999999')
        }
        .width('100%').layoutWeight(1).justifyContent(FlexAlign.Center)
      }
    }
    .width('100%').height('100%').backgroundColor('#f5f6fa')
  }

  // 分身详情卡片（可折叠）
  @Builder
  PersonaCard(pr: PersonaResult) {
    Column() {
      // 标题行
      Row() {
        Text(`${pr.name}（权重：${pr.weight.toFixed(2)}）`)
          .fontSize(15).fontWeight(FontWeight.Medium).fontColor('#2c3e50').layoutWeight(1)
        Text(`f*=${(pr.f_star * 100).toFixed(1)}%`)
          .fontSize(14).fontWeight(FontWeight.Bold)
          .fontColor(pr.f_star > 0.5 ? '#27ae60' : pr.f_star >= 0 ? '#f39c12' : '#e74c3c')
      }
      .width('100%').padding(16)
      .onClick(() => this.expandAllPersonas = !this.expandAllPersonas) // 点击标题行切换展开

      // 展开详情
      if (this.expandAllPersonas) {
        Column() {
          Text(`胜率 p：${pr.p.toFixed(4)}`).fontSize(12).fontColor('#555').margin({ top: 4 })
          Text(`败率 q：${pr.q.toFixed(4)}`).fontSize(12).fontColor('#555')
          Text(`赔率 b：${pr.b.toFixed(2)}`).fontSize(12).fontColor('#555')
          Text(`推理过程：${pr.reasoning}`).fontSize(12).fontColor('#555').lineHeight(18).margin({ top: 4 })

          Row() {
            Button() {
              Text('📋 复制该分身报告').fontSize(11).fontColor('#27ae60')
            }
            .backgroundColor(Color.Transparent).borderRadius(4).padding({ left: 8, right: 8 })
            .onClick(() => this.copyPersonaReport(pr))
          }
          .width('100%').justifyContent(FlexAlign.End).margin({ top: 8 })
        }
        .width('100%').padding(16).backgroundColor('#f8f9fa')
      }
      // 分身级反馈入口（Phase 4.2.3 新增）
      Row() {
        Button() {
          Text('💬 对此分身的建议反馈').fontSize(11).fontColor('#3498db')
        }
        .backgroundColor(Color.Transparent).borderRadius(4).padding({ left: 8, right: 8 })
        .onClick(() => this.openPersonaFeedback(pr))
      }
      .width('100%').justifyContent(FlexAlign.End).margin({ top: 4 })
    }
    .width('100%').backgroundColor('#ffffff').borderRadius(12).margin({ top: 8 })
    .shadow({ radius: 2, color: '#00000010', offsetX: 0, offsetY: 1 })
  }

  // 复制单个分身报告
  copyPersonaReport(pr: PersonaResult) {
    const text = `【${pr.name}（权重：${pr.weight.toFixed(2)}）独立报告】\n胜率 p：${pr.p.toFixed(4)}\n败率 q：${pr.q.toFixed(4)}\n赔率 b：${pr.b.toFixed(2)}\n最优下注比例 f*：${pr.f_star.toFixed(4)}\n\n推理过程：\n${pr.reasoning}\n\n—— DecisionMate`;
    const pasteData = pasteboard.createData(pasteboard.MIMETYPE_TEXT_PLAIN, text);
    pasteboard.getSystemPasteboard().setData(pasteData, (err) => {
      if (err) console.error('复制失败: ' + JSON.stringify(err));
    });
  }

  // 格式化报告文本（重写以支持多分身）
  formatReportText(): string {
    if (!this.report) return '';
    const report = this.report;
    const separator = '━━━━━━━━━━━━━━━━━━━━━━━━━━';
    let text = '【决策分析报告】\n' + separator + '\n\n';
    text += `📋 综合建议\n${report.recommendation}\n\n${separator}\n\n`;
    text += `📊 关键指标\n  • 最优下注比例：${(report.f_star * 100).toFixed(1)}%\n  • 风险等级：${report.risk_level}\n  • 场景类型：${report.scenario_type}\n\n${separator}\n\n`;

    if (report.persona_results && report.persona_results.length > 0) {
      for (const pr of report.persona_results) {
        text += `👤 ${pr.name} （权重：${pr.weight.toFixed(2)}） (f*=${(pr.f_star * 100).toFixed(1)}%)\n  推理：${pr.reasoning}\n\n`;
        text += `${separator}\n\n`;
      }
      // 多分身模式下也追加量化分析、风险评估、计算过程
      text += `🔢 量化分析（会商摘要）\n${report.quant_opinion}\n\n`;
      text += `${separator}\n\n`;
      text += `🛡️ 风险评估\n${report.risk_opinion}\n\n`;
      text += `${separator}\n\n`;
      text += `📝 计算过程\n${report.calculation_detail}\n\n`;
    } else {
      text += `🔢 量化分析\n${report.quant_opinion}\n\n`;
      text += `🛡️ 风险评估\n${report.risk_opinion}\n\n`;
      text += `📝 计算过程\n${report.calculation_detail}\n\n`;
    }

    if (report.scene_result && report.scene_result.scene_recognized) {
      const scene = report.scene_result;
      text += `${separator}\n📅 分阶段策略：${scene.scene_type}\n时间线：\n${scene.timeline_summary}\n\n`;
      scene.strategies.forEach((s, i) => {
        text += `${i + 1}. ${s.strategy_name}（${s.date_range}）\n   ${s.suggestion}\n   📌 ${s.reference}\n\n`;
      });
      text += `${scene.reasoning}\n`;
    }

    text += `${separator}\n⚠️ 以上分析仅供参考，最终决策权在你手中\n—— DecisionMate`;
    return text;
  }

  /**
   * 复制报告全文到系统剪贴板
   */
  copyReportToClipboard() {
    try {
      const text = this.formatReportText();
      if (!text) return;
      const pasteData = pasteboard.createData(pasteboard.MIMETYPE_TEXT_PLAIN, text);
      pasteboard.getSystemPasteboard().setData(pasteData, (err) => {
        if (err) {
          console.error('复制失败: ' + JSON.stringify(err));
        } else {
          this.copyButtonText = '已复制 ✓';
          setTimeout(() => this.copyButtonText = '复制全文', 1500);
        }
      });
    } catch (error) {
      console.error('copyReportToClipboard error: ' + JSON.stringify(error));
    }
  }

  @Builder
  buildCard(title: string, content: string, bgColor: string) {
    Column() {
      Text(title).fontSize(14).fontWeight(FontWeight.Medium).fontColor('#2c3e50').margin({ bottom: 8 })
      Text(content).fontSize(13).fontColor('#555555').lineHeight(22).width('100%')
    }
    .width('100%').backgroundColor(bgColor).borderRadius(12).padding(16).margin({ top: 12 })
  }
}