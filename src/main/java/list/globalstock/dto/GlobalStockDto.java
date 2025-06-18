package list.globalstock.dto;

public class GlobalStockDto {

    private String name;
    private String price;
    private String rate;

    public GlobalStockDto(String name, String price, String rate){
        this.name = name;
        this.price = price;
        this.rate = rate;
    }

    // Getters & Setters
    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }

    public String getPrice() {
        return price;
    }
    public void setPrice(String price) {
        this.price = price;
    }

    public String getRate() {
        return rate;
    }
    public void setRate(String rate) {
        this.rate = rate;
    }
}
