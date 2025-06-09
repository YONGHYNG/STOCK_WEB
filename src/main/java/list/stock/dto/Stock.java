package list.stock.dto;

public class Stock {

    private String name;
    private String price;
    private String changeRate;

    //생성자, getter, setter
    public Stock(String name, String price, String changeRate) {
        this.name = name;
        this.price = price;
        this.changeRate = changeRate;
    }

    public String getName() {
        return name;
    }


    public String getPrice() {
        return price;
    }

    public String getChangeRate() {
        return changeRate;
    }
}
