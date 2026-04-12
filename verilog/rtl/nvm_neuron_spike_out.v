module nvm_neuron_spike_out (
  input             wb_clk_i,
  input             wb_rst_i,
  input             wbs_cyc_i,
  input             wbs_stb_i,
  input             wbs_we_i,
  input       [3:0] wbs_sel_i,
  input      [31:0] wbs_adr_i,
  input      [31:0] wbs_dat_i,
  output reg        wbs_ack_o,
  output reg [31:0] wbs_dat_o
  );

  // 4 x 16-bit entries: sram[0]=spikes[15:0], sram[1]=spikes[31:16],
  //                     sram[2]=spikes[47:32], sram[3]=spikes[63:48]
  reg [15:0] sram [3:0];
  wire [1:0] addr = wbs_adr_i[2:1];

  always @(posedge wb_clk_i or posedge wb_rst_i) begin
    if (wb_rst_i) begin
      wbs_ack_o <= 1'b0;
      wbs_dat_o <= 32'b0;
      sram[0]   <= 16'b0;
      sram[1]   <= 16'b0;
      sram[2]   <= 16'b0;
      sram[3]   <= 16'b0;
    end
    else if (wbs_cyc_i && wbs_stb_i) begin
      wbs_ack_o <= 1'b1;
      if (wbs_we_i) begin
        // Write 32 bits atomically: addr selects the PAIR (sram[2*addr], sram[2*addr+1])
        // wbs_dat_i[15:0]  -> lower sram entry  (spike bits  0-15 or 32-47)
        // wbs_dat_i[31:16] -> upper sram entry  (spike bits 16-31 or 48-63)
        // addr[0] (wbs_adr_i[1]) selects lower/upper pair:
        //   wbs_adr_i[2]=0 -> write sram[0] (lo 16 bits) and sram[1] (hi 16 bits)
        //   wbs_adr_i[2]=1 -> write sram[2] and sram[3]
        if (!wbs_adr_i[2]) begin
          if (wbs_sel_i[0]) sram[0][ 7:0] <= wbs_dat_i[ 7: 0];
          if (wbs_sel_i[1]) sram[0][15:8] <= wbs_dat_i[15: 8];
          if (wbs_sel_i[2]) sram[1][ 7:0] <= wbs_dat_i[23:16];
          if (wbs_sel_i[3]) sram[1][15:8] <= wbs_dat_i[31:24];
        end else begin
          if (wbs_sel_i[0]) sram[2][ 7:0] <= wbs_dat_i[ 7: 0];
          if (wbs_sel_i[1]) sram[2][15:8] <= wbs_dat_i[15: 8];
          if (wbs_sel_i[2]) sram[3][ 7:0] <= wbs_dat_i[23:16];
          if (wbs_sel_i[3]) sram[3][15:8] <= wbs_dat_i[31:24];
        end
      end
      else begin
        // Read: addr[2]=0 -> {sram[1],sram[0]}; addr[2]=1 -> {sram[3],sram[2]}
        wbs_dat_o <= wbs_adr_i[2] ? {sram[3], sram[2]} : {sram[1], sram[0]};
      end
    end
    else begin
      wbs_ack_o <= 1'b0;
      wbs_dat_o <= 32'b0;
    end
  end

endmodule
