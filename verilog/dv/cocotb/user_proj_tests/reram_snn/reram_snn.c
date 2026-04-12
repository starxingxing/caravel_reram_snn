#include <firmware_apis.h>

void main() {
    // Enable management GPIOs as output for handshaking
    ManagmentGpio_outputEnable();
    ManagmentGpio_write(0);

    // Configure all GPIOs to be controlled by the User Project
    GPIOs_configureAll(GPIO_MODE_USER_STD_OUT_MONITORED);
    GPIOs_loadConfigs();

    // Enable the Wishbone interface to the User Project
    // Without this, the SoC will not acknowledge Wishbone transactions
    User_enableIF(1);

    // Signal to the Python testbench that the SoC is ready
    ManagmentGpio_write(1);

    // Keep the CPU alive while Python drives the test
    while(1) {
        __asm__ volatile ("nop");
    }
}
