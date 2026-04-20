
<table>
  <tr>
    <td align="center"><img src="bm-lab-logo-white.jpg" alt="BM LABS Logo" width="200"/></td>
    <td align="center"><img src="chip_foundry_logo.png" alt="Chipfoundry Logo" width="200"/></td>
  </tr>
</table>

# Caravel User Neuromorphic X1 Example

This project demonstrates the straightforward integration of a commercial Neuromorphic X1 within the `user_project_wrapper` using the IPM (IP Manager) tool.

## Get Started Quickly

### Follow these steps to set up your environment and harden the Neuromorphic X1:

1. **Clone the Repository:**

```
git clone https://github.com/Baavanes/caravel_reram_snn.git
```
2. **Prepare Your Environment:**

```
cd caravel_reram_snn
make setup
```
3. **Install IPM:**

```
pip install cf-ipm
```
4. **Install the Neuromorphic X1 IP:**

```
ipm install Neuromorphic_X1_32x32
Replace the hdl folder inside ip/Neuromorphic_X1_32x32 with folder hdl(replace_in_ip_hdl_folder)
Rename the folder hdl(replace_in_ip_hdl_folder) inside ip/Neuromorphic_X1_32x32 to hdl
```
5. **Run Caravel cocotb simulation**

```
make cocotb-verify-ram_word-rtl
```

6. **Harden the User Project Wrapper using librelane/openlane2:**

```
make user_project_wrapper
```

Details about the Neuromorphic X1 IP itself are available in the [Neuromorphic X1 documentation](https://github.com/BMsemi/Neuromorphic_X1_32x32).
