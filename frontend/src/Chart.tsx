import { useEffect, useRef } from "react";
import * as echarts from "echarts/core";
import { LineChart } from "echarts/charts";
import { GridComponent, TooltipComponent } from "echarts/components";
import { CanvasRenderer } from "echarts/renderers";
import type { Stats } from "./types";
echarts.use([LineChart, GridComponent, TooltipComponent, CanvasRenderer]);
export default function Chart({ data }: { data: Stats["trend"] }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!ref.current) return;
    const chart = echarts.init(ref.current);
    chart.setOption({
      textStyle: { fontFamily: "inherit" },
      grid: { left: 40, right: 16, top: 18, bottom: 30 },
      tooltip: { trigger: "axis", valueFormatter: (v: number) => v + "%" },
      xAxis: {
        type: "category",
        data: data.map((x) =>
          new Date(x.date).toLocaleDateString("zh-CN", {
            month: "numeric",
            day: "numeric",
          }),
        ),
        axisLine: { lineStyle: { color: "#e4e9e8" } },
        axisTick: { show: false },
        axisLabel: { color: "#87958f" },
      },
      yAxis: {
        type: "value",
        min: 0,
        max: 100,
        axisLabel: { formatter: "{value}%", color: "#87958f" },
        splitLine: { lineStyle: { color: "#edf0ed", type: "dashed" } },
      },
      series: [
        {
          data: data.map((x) => x.score),
          type: "line",
          smooth: 0.25,
          symbol: "circle",
          symbolSize: 7,
          lineStyle: { color: "#258675", width: 3 },
          itemStyle: { color: "#258675", borderWidth: 3, borderColor: "#fff" },
          areaStyle: {
            color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
              { offset: 0, color: "#25867530" },
              { offset: 1, color: "#25867500" },
            ]),
          },
        },
      ],
    });
    const resize = new ResizeObserver(() => chart.resize());
    resize.observe(ref.current);
    return () => {
      resize.disconnect();
      chart.dispose();
    };
  }, [data]);
  return (
    <div
      ref={ref}
      className="chart"
      role="img"
      aria-label={`模拟成绩趋势，共 ${data.length} 次考试`}
    />
  );
}
